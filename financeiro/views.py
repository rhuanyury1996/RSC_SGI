"""Financeiro do SGI (portado do Arcturus). Acesso: só o CEO."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ledger.models import Employee, Entity, Equipment, Recurrence, Transaction
from ledger.money import cents_to_reais_str
from ledger.services import depreciation_as_of, expand_recurrence, project_entity_tax

from .acesso import somente_ceo
from .forms import TransactionForm

workspace_required = somente_ceo


def _voltar(request: HttpRequest, padrao: str = "financeiro:lancamentos"):
    """Volta para a página anterior só se for do próprio site."""
    ref = request.META.get("HTTP_REFERER") or ""
    if ref and url_has_allowed_host_and_scheme(
        ref, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(ref)
    return redirect(padrao)


@somente_ceo
@require_POST
def set_entity_filter(request: HttpRequest) -> HttpResponse:
    request.session["entity_filter"] = request.POST.get("entity_filter", "all")
    return _voltar(request, "financeiro:painel")

ENTRY_ACTIONS = [
    {
        "kind": Transaction.EntryKind.INCOME,
        "title": "Receita",
        "desc": "Prestação de serviços, vendas e outras entradas",
        "icon": "trending-up",
        "tone": "good",
    },
    {
        "kind": Transaction.EntryKind.PROJECTED_SALE,
        "title": "Venda projetada",
        "desc": "Possível receita — só consolida quando confirmada",
        "icon": "pin",
        "tone": "warn",
    },
    {
        "kind": Transaction.EntryKind.FIXED_EXPENSE,
        "title": "Despesa fixa",
        "desc": "Aluguel, assinaturas, custos recorrentes",
        "icon": "building",
        "tone": "ink",
    },
    {
        "kind": Transaction.EntryKind.VARIABLE_EXPENSE,
        "title": "Despesa variável",
        "desc": "Gastos pontuais e operacionais",
        "icon": "shuffle",
        "tone": "ink",
    },
    {
        "kind": Transaction.EntryKind.PROJECTED_PURCHASE,
        "title": "Compra projetada",
        "desc": "Aquisições planejadas ainda não realizadas",
        "icon": "cart",
        "tone": "warn",
    },
    {
        "kind": Transaction.EntryKind.SALARY,
        "title": "Salário",
        "desc": "Pró-labore, salários e folha",
        "icon": "users",
        "tone": "ink",
    },
    {
        "kind": Transaction.EntryKind.TAX,
        "title": "Imposto a pagar",
        "desc": "DAS, ISS, IR e demais obrigações",
        "icon": "percent",
        "tone": "bad",
    },
]



def _entity_filter_ids(request: HttpRequest) -> list[int] | None:
    """None = consolidado (todas)."""
    raw = request.session.get("entity_filter", "all")
    if raw in (None, "", "all"):
        return None
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return None


def _tx_qs(request: HttpRequest):
    ws = request.workspace
    qs = Transaction.objects.for_workspace(ws).select_related(
        "account", "account__entity", "category", "project", "employee"
    )
    entity_ids = _entity_filter_ids(request)
    if entity_ids:
        qs = qs.filter(account__entity_id__in=entity_ids)
    return qs




@workspace_required
def dashboard(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_end = month_start + relativedelta(months=1, days=-1)
    qs = _tx_qs(request)

    paid = qs.filter(status=Transaction.Status.PAID)
    balance = paid.aggregate(s=Sum("amount_cents"))["s"] or 0
    a_receber = (
        qs.filter(
            entry_kind=Transaction.EntryKind.INCOME,
            due_date__gte=month_start,
            due_date__lte=month_end,
            status=Transaction.Status.PENDING,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    a_pagar = abs(
        qs.filter(
            amount_cents__lt=0,
            due_date__gte=month_start,
            due_date__lte=month_end,
            status=Transaction.Status.PENDING,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    horizon_end = month_start + relativedelta(months=12, days=-1)
    comprometido = abs(
        qs.filter(
            amount_cents__lt=0,
            due_date__gte=today,
            due_date__lte=horizon_end,
            status=Transaction.Status.PENDING,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )

    # Fluxo 12 meses (persistidos + recorrências virtuais)
    cashflow = []
    cursor = month_start
    by_month: dict[tuple[int, int], dict[str, int]] = defaultdict(
        lambda: {"in": 0, "out": 0}
    )
    for tx in qs.filter(due_date__gte=month_start, due_date__lte=horizon_end):
        if tx.entry_kind == Transaction.EntryKind.PROJECTED_SALE:
            continue
        key = (tx.due_date.year, tx.due_date.month)
        if tx.amount_cents > 0:
            by_month[key]["in"] += tx.amount_cents
        else:
            by_month[key]["out"] += abs(tx.amount_cents)

    entity_ids = _entity_filter_ids(request)
    for rec in Recurrence.objects.for_workspace(request.workspace).filter(active=True):
        if entity_ids and rec.account.entity_id not in entity_ids:
            continue
        existing = set(
            Transaction.objects.filter(recurrence=rec).values_list("due_date", flat=True)
        )
        for occ in expand_recurrence(rec, range_start=month_start, range_end=horizon_end):
            if occ["due_date"] in existing:
                continue
            key = (occ["due_date"].year, occ["due_date"].month)
            if occ["amount_cents"] > 0:
                by_month[key]["in"] += occ["amount_cents"]
            else:
                by_month[key]["out"] += abs(occ["amount_cents"])

    MONTHS_PT = [
        "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez",
    ]
    max_bar = 1
    for i in range(12):
        key = (cursor.year, cursor.month)
        data = by_month[key]
        cashflow.append(
            {
                "label": f"{MONTHS_PT[cursor.month - 1]}/{str(cursor.year)[2:]}",
                "income": data["in"],
                "expense": data["out"],
                "income_h": 0,
                "expense_h": 0,
            }
        )
        cursor += relativedelta(months=1)
    # second pass for heights with known max
    max_bar = max(
        [1]
        + [c["income"] for c in cashflow]
        + [c["expense"] for c in cashflow]
    )
    for c in cashflow:
        c["income_h"] = max(4, int(c["income"] / max_bar * 140)) if c["income"] else 2
        c["expense_h"] = max(4, int(c["expense"] / max_bar * 140)) if c["expense"] else 2

    # Despesas por categoria no mês
    expense_by_cat = (
        qs.filter(
            amount_cents__lt=0,
            due_date__gte=month_start,
            due_date__lte=month_end,
        )
        .values("category__name")
        .annotate(total=Sum("amount_cents"))
        .order_by("total")
    )
    cat_rows = []
    cat_total = sum(abs(r["total"]) for r in expense_by_cat) or 1
    for r in expense_by_cat[:8]:
        val = abs(r["total"])
        cat_rows.append(
            {
                "name": r["category__name"],
                "cents": val,
                "pct": round(val / cat_total * 100, 1),
            }
        )

    # Receitas por categoria no mês (somente consolidadas)
    income_by_cat = (
        qs.filter(
            entry_kind=Transaction.EntryKind.INCOME,
            due_date__gte=month_start,
            due_date__lte=month_end,
        )
        .values("category__name")
        .annotate(total=Sum("amount_cents"))
        .order_by("-total")
    )
    income_cat_rows = []
    income_cat_total = sum(r["total"] for r in income_by_cat) or 1
    for r in income_by_cat[:8]:
        val = r["total"]
        income_cat_rows.append(
            {
                "name": r["category__name"],
                "cents": val,
                "pct": round(val / income_cat_total * 100, 1),
            }
        )

    # Folha / custo por funcionário (mês)
    salary_qs = qs.filter(
        entry_kind=Transaction.EntryKind.SALARY,
        due_date__gte=month_start,
        due_date__lte=month_end,
    )
    payroll_total = abs(salary_qs.aggregate(s=Sum("amount_cents"))["s"] or 0)
    by_employee = (
        salary_qs.values("employee_id", "employee__name")
        .annotate(total=Sum("amount_cents"), n=Count("id"))
        .order_by("total")
    )
    employee_rows = []
    for r in by_employee:
        val = abs(r["total"] or 0)
        employee_rows.append(
            {
                "name": r["employee__name"] or "Sem funcionário",
                "cents": val,
                "count": r["n"],
                "pct": round(val / payroll_total * 100, 1) if payroll_total else 0,
            }
        )
    # Inclui funcionários ativos sem lançamento no mês (custo 0) para visão completa
    named = {r["name"] for r in employee_rows if r["name"] != "Sem funcionário"}
    for emp in Employee.objects.for_workspace(request.workspace).filter(active=True):
        if emp.name not in named:
            employee_rows.append(
                {"name": emp.name, "cents": 0, "count": 0, "pct": 0}
            )
    employee_rows.sort(key=lambda r: (-r["cents"], r["name"]))

    # Breakdown por tipo de lançamento (mês)
    kind_totals_qs = (
        qs.filter(due_date__gte=month_start, due_date__lte=month_end)
        .values("entry_kind")
        .annotate(total=Sum("amount_cents"), n=Count("id"))
    )
    kind_label = dict(Transaction.EntryKind.choices)
    kind_rows = []
    for r in kind_totals_qs:
        kind_rows.append(
            {
                "kind": r["entry_kind"],
                "label": kind_label.get(r["entry_kind"], r["entry_kind"]),
                "cents": r["total"] or 0,
                "abs_cents": abs(r["total"] or 0),
                "count": r["n"],
            }
        )
    kind_rows.sort(key=lambda r: -r["abs_cents"])

    # Por entidade (mês)
    entity_month = (
        qs.filter(due_date__gte=month_start, due_date__lte=month_end)
        .values("account__entity__name")
        .annotate(
            income=Sum(
                "amount_cents",
                filter=Q(entry_kind=Transaction.EntryKind.INCOME),
            ),
            projected=Sum(
                "amount_cents",
                filter=Q(entry_kind=Transaction.EntryKind.PROJECTED_SALE),
            ),
            expense=Sum("amount_cents", filter=Q(amount_cents__lt=0)),
        )
        .order_by("account__entity__name")
    )
    entity_rows = []
    for r in entity_month:
        inc = r["income"] or 0
        proj = r["projected"] or 0
        exp = abs(r["expense"] or 0)
        entity_rows.append(
            {
                "name": r["account__entity__name"],
                "income": inc,
                "projected": proj,
                "expense": exp,
                "net": inc - exp,
                "pipeline": inc + proj,
            }
        )

    month_income = (
        qs.filter(
            entry_kind=Transaction.EntryKind.INCOME,
            due_date__gte=month_start,
            due_date__lte=month_end,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    month_projected = (
        qs.filter(
            entry_kind=Transaction.EntryKind.PROJECTED_SALE,
            due_date__gte=month_start,
            due_date__lte=month_end,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    month_pipeline = month_income + month_projected
    month_expense = abs(
        qs.filter(
            amount_cents__lt=0,
            due_date__gte=month_start,
            due_date__lte=month_end,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    month_net = month_income - month_expense

    upcoming = qs.filter(
        status=Transaction.Status.PENDING, due_date__gte=today - relativedelta(days=7)
    ).order_by("due_date")[:8]

    overdue_count = qs.filter(
        status=Transaction.Status.PENDING, due_date__lt=today
    ).count()

    # Patrimônio por entidade
    patrimony = []
    entities = Entity.objects.for_workspace(request.workspace).filter(active=True)
    if entity_ids:
        entities = entities.filter(id__in=entity_ids)
    for ent in entities:
        items = Equipment.objects.for_workspace(request.workspace).filter(
            owner_entity=ent, active=True
        )
        book = sum(
            depreciation_as_of(eq, today)["book_value_cents"] for eq in items
        )
        acquis = sum(eq.acquisition_value_cents for eq in items)
        patrimony.append(
            {"entity": ent, "book": book, "acquisition": acquis, "count": items.count()}
        )

    month_revenue = month_income
    month_taxes = abs(
        qs.filter(
            entry_kind=Transaction.EntryKind.TAX,
            due_date__gte=month_start,
            due_date__lte=month_end,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    company_qs = Entity.objects.for_workspace(request.workspace).filter(
        kind=Entity.Kind.COMPANY, active=True
    )
    if entity_ids:
        company_qs = company_qs.filter(id__in=entity_ids)
    company = company_qs.first()
    rate_bps = company.effective_tax_rate_bps if company else 1700
    tax_proj = project_entity_tax(
        revenue_cents=month_revenue,
        taxes_booked_cents=month_taxes,
        rate_bps=rate_bps,
    )
    kind_counts = {
        row["entry_kind"]: row["c"]
        for row in qs.filter(due_date__gte=month_start, due_date__lte=month_end)
        .values("entry_kind")
        .annotate(c=Count("id"))
    }

    return render(
        request,
        "financeiro/painel.html",
        {
            "balance": balance,
            "a_receber": a_receber,
            "a_pagar": a_pagar,
            "comprometido": comprometido,
            "month_income": month_income,
            "month_expense": month_expense,
            "month_net": month_net,
            "month_projected": month_projected,
            "month_pipeline": month_pipeline,
            "payroll_total": payroll_total,
            "employee_rows": employee_rows,
            "income_cat_rows": income_cat_rows,
            "kind_rows": kind_rows,
            "entity_rows": entity_rows,
            "month_label": f"{MONTHS_PT[month_start.month - 1]}/{month_start.year}",
            "cashflow": cashflow,
            "cat_rows": cat_rows,
            "upcoming": upcoming,
            "overdue_count": overdue_count,
            "patrimony": patrimony,
            "tax_proj": tax_proj,
            "entry_actions": ENTRY_ACTIONS,
            "kind_counts": kind_counts,
            "money": cents_to_reais_str,
            "entities": Entity.objects.for_workspace(request.workspace).filter(active=True),
            "entity_filter": request.session.get("entity_filter", "all"),
        },
    )



def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _period_bounds(
    period: str,
    today: date,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date | None, date | None]:
    if period in {"", "all"}:
        return None, None
    if period == "7d":
        return today - relativedelta(days=6), today
    if period == "30d":
        return today - relativedelta(days=29), today
    if period == "month":
        start = today.replace(day=1)
        end = start + relativedelta(months=1, days=-1)
        return start, end
    if period == "last_month":
        end = today.replace(day=1) - relativedelta(days=1)
        start = end.replace(day=1)
        return start, end
    if period == "year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    if period == "custom":
        return date_from, date_to
    return None, None


def _filtered_transactions(request: HttpRequest):
    """Aplica filtros da lista de lançamentos (período, tipo, fluxo, busca)."""
    today = timezone.localdate()
    qs = _tx_qs(request)

    period = (request.GET.get("period") or "all").strip()
    date_from = _parse_iso_date(request.GET.get("date_from"))
    date_to = _parse_iso_date(request.GET.get("date_to"))
    if period != "custom":
        date_from = None
        date_to = None
    elif not date_from and not date_to:
        period = "all"
    start, end = _period_bounds(period, today, date_from, date_to)
    if start:
        qs = qs.filter(due_date__gte=start)
    if end:
        qs = qs.filter(due_date__lte=end)

    base_qs = qs
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    kind = request.GET.get("kind")
    if kind:
        qs = qs.filter(entry_kind=kind)
    flow = request.GET.get("flow")
    if flow == "income":
        qs = qs.filter(entry_kind=Transaction.EntryKind.INCOME)
    elif flow == "projected":
        qs = qs.filter(entry_kind=Transaction.EntryKind.PROJECTED_SALE)
    elif flow == "expense":
        qs = qs.filter(amount_cents__lt=0)
    q = request.GET.get("q")
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(notes__icontains=q))

    return {
        "qs": qs,
        "base_qs": base_qs,
        "period": period,
        "start": start,
        "end": end,
        "date_from": date_from,
        "date_to": date_to,
        "status": status or "",
        "kind": kind or "",
        "flow": flow or "",
        "q": q or "",
    }


@workspace_required
def transaction_list(request: HttpRequest) -> HttpResponse:
    f = _filtered_transactions(request)
    qs = f["qs"]
    base_qs = f["base_qs"]
    period = f["period"]
    start, end = f["start"], f["end"]
    date_from, date_to = f["date_from"], f["date_to"]
    status, kind, flow, q = f["status"], f["kind"], f["flow"], f["q"]

    counts = {
        "all": base_qs.count(),
        "income": base_qs.filter(entry_kind=Transaction.EntryKind.INCOME).count(),
        "projected": base_qs.filter(
            entry_kind=Transaction.EntryKind.PROJECTED_SALE
        ).count(),
        "expense": base_qs.filter(amount_cents__lt=0).count(),
        "pending": base_qs.filter(status=Transaction.Status.PENDING).count(),
        "paid": base_qs.filter(status=Transaction.Status.PAID).count(),
    }
    income_cents = (
        qs.filter(entry_kind=Transaction.EntryKind.INCOME).aggregate(
            s=Sum("amount_cents")
        )["s"]
        or 0
    )
    projected_cents = (
        qs.filter(entry_kind=Transaction.EntryKind.PROJECTED_SALE).aggregate(
            s=Sum("amount_cents")
        )["s"]
        or 0
    )
    expense_cents = (
        qs.filter(amount_cents__lt=0).aggregate(s=Sum("amount_cents"))["s"] or 0
    )
    balance_cents = income_cents + expense_cents

    period_label = {
        "all": "Todo o período",
        "7d": "Últimos 7 dias",
        "30d": "Últimos 30 dias",
        "month": "Este mês",
        "last_month": "Mês passado",
        "year": "Este ano",
        "custom": "Personalizado",
    }.get(period, "Todo o período")
    if start or end:
        period_range = (
            f"{start.strftime('%d/%m/%Y') if start else '…'} – "
            f"{end.strftime('%d/%m/%Y') if end else '…'}"
        )
    else:
        period_range = ""

    return render(
        request,
        "financeiro/lancamentos.html",
        {
            "transactions": qs[:200],
            "money": cents_to_reais_str,
            "q": q,
            "status": status,
            "kind": kind,
            "flow": flow,
            "period": period,
            "date_from": (start.isoformat() if start else "")
            if period != "custom"
            else (date_from.isoformat() if date_from else ""),
            "date_to": (end.isoformat() if end else "")
            if period != "custom"
            else (date_to.isoformat() if date_to else ""),
            "period_label": period_label,
            "period_range": period_range,
            "counts": counts,
            "totals": {
                "income_cents": income_cents,
                "projected_cents": projected_cents,
                "pipeline_cents": income_cents + projected_cents,
                "expense_cents": expense_cents,
                "balance_cents": balance_cents,
                "shown": min(qs.count(), 200),
                "filtered": qs.count(),
            },
            "entry_kinds": Transaction.EntryKind.choices,
            "entities": Entity.objects.for_workspace(request.workspace).filter(active=True),
            "entity_filter": request.session.get("entity_filter", "all"),
            "export_query": request.GET.urlencode(),
            "periodos": [
                ("all", "Tudo"), ("7d", "7 dias"), ("30d", "30 dias"),
                ("month", "Este mês"), ("last_month", "Mês passado"), ("year", "Este ano"),
            ],
        },
    )


@workspace_required
def transaction_export_xlsx(request: HttpRequest) -> HttpResponse:
    """Exporta lançamentos filtrados para Excel (.xlsx)."""
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Font

    f = _filtered_transactions(request)
    qs = f["qs"].select_related(
        "account", "account__entity", "category", "category__parent", "employee", "project"
    ).order_by("-due_date", "-id")

    wb = Workbook()
    ws = wb.active
    ws.title = "Lançamentos"
    headers = [
        "ID",
        "Descrição",
        "Tipo",
        "Status",
        "Competência",
        "Vencimento",
        "Pago em",
        "Valor (R$)",
        "Valor (centavos)",
        "Conta",
        "Entidade",
        "Categoria",
        "Natureza",
        "Funcionário",
        "Projeto",
        "Observações",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for tx in qs.iterator(chunk_size=500):
        cat = str(tx.category) if tx.category_id else ""
        ws.append(
            [
                tx.id,
                tx.description,
                tx.get_entry_kind_display(),
                tx.get_status_display(),
                tx.competence_date.isoformat() if tx.competence_date else "",
                tx.due_date.isoformat() if tx.due_date else "",
                tx.paid_at.isoformat() if tx.paid_at else "",
                round(tx.amount_cents / 100, 2),
                tx.amount_cents,
                tx.account.name if tx.account_id else "",
                tx.account.entity.name if tx.account_id else "",
                cat,
                tx.get_nature_display(),
                tx.employee.name if tx.employee_id else "",
                tx.project.name if tx.project_id else "",
                tx.notes or "",
            ]
        )

    # Resumo
    summary = wb.create_sheet("Resumo")
    summary.append(["Campo", "Valor"])
    summary["A1"].font = Font(bold=True)
    summary["B1"].font = Font(bold=True)
    income = (
        f["qs"].filter(entry_kind=Transaction.EntryKind.INCOME).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    projected = (
        f["qs"]
        .filter(entry_kind=Transaction.EntryKind.PROJECTED_SALE)
        .aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )
    expense = f["qs"].filter(amount_cents__lt=0).aggregate(s=Sum("amount_cents"))["s"] or 0
    summary.append(["Workspace", request.workspace.name])
    summary.append(["Período", f["period"]])
    summary.append(["De", f["start"].isoformat() if f["start"] else ""])
    summary.append(["Até", f["end"].isoformat() if f["end"] else ""])
    summary.append(["Qtd. lançamentos", f["qs"].count()])
    summary.append(["Receitas (R$)", round(income / 100, 2)])
    summary.append(["Vendas projetadas (R$)", round(projected / 100, 2)])
    summary.append(["Receita + projetada (R$)", round((income + projected) / 100, 2)])
    summary.append(["Saídas (R$)", round(expense / 100, 2)])
    summary.append(["Saldo líquido (R$)", round((income + expense) / 100, 2)])
    summary.append(["Gerado em", timezone.localtime().isoformat(timespec="seconds")])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
    filename = f"sgi_financeiro_{stamp}.xlsx"
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@workspace_required
def entry_hub(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "financeiro/novo.html",
        {"entry_actions": ENTRY_ACTIONS},
    )


@workspace_required
def transaction_create(request: HttpRequest) -> HttpResponse:
    kind = request.GET.get("kind") or request.POST.get("entry_kind") or Transaction.EntryKind.VARIABLE_EXPENSE
    valid = {c.value for c in Transaction.EntryKind}
    if kind not in valid:
        kind = Transaction.EntryKind.VARIABLE_EXPENSE
    title_map = dict(Transaction.EntryKind.choices)
    title = f"Nova {title_map[kind].lower()}" if kind != Transaction.EntryKind.INCOME else "Nova receita"
    if kind == Transaction.EntryKind.INCOME:
        title = "Nova receita"
    else:
        title = f"Novo — {title_map[kind]}"

    if request.method == "POST":
        form = TransactionForm(request.POST, workspace=request.workspace, entry_kind=kind)
        if form.is_valid():
            form.save()
            n = getattr(form, "created_count", 1) or 1
            if getattr(form, "recurrence", None) and n > 1:
                messages.success(
                    request,
                    f"Recorrência criada com {n} lançamentos no período.",
                )
            elif getattr(form, "recurrence", None):
                messages.success(request, "Recorrência criada.")
            else:
                messages.success(request, "Lançamento criado.")
            return redirect("financeiro:lancamentos")
    else:
        today = timezone.localdate()
        form = TransactionForm(
            workspace=request.workspace,
            entry_kind=kind,
            initial={
                "competence_date": today,
                "due_date": today,
                "nature": Transaction.Nature.PROFESSIONAL,
                "status": Transaction.Status.PENDING,
            },
        )
    return render(
        request,
        "financeiro/lancamento_form.html",
        {
            "form": form,
            "title": title,
            "entry_kind": kind,
            "entry_kind_label": title_map[kind],
        },
    )


@workspace_required
def transaction_edit(request: HttpRequest, pk: int) -> HttpResponse:
    tx = get_object_or_404(Transaction, pk=pk, workspace=request.workspace)
    if request.method == "POST":
        form = TransactionForm(
            request.POST,
            instance=tx,
            workspace=request.workspace,
            entry_kind=tx.entry_kind,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Lançamento atualizado.")
            return redirect("financeiro:lancamentos")
    else:
        form = TransactionForm(
            instance=tx, workspace=request.workspace, entry_kind=tx.entry_kind
        )
    return render(
        request,
        "financeiro/lancamento_form.html",
        {
            "form": form,
            "title": "Editar lançamento",
            "transaction": tx,
            "entry_kind": tx.entry_kind,
            "entry_kind_label": tx.get_entry_kind_display(),
        },
    )


@workspace_required
@require_POST
def transaction_toggle_status(request: HttpRequest, pk: int) -> HttpResponse:
    tx = get_object_or_404(Transaction, pk=pk, workspace=request.workspace)
    if tx.status == Transaction.Status.PENDING:
        tx.status = Transaction.Status.PAID
        tx.paid_at = timezone.localdate()
    else:
        tx.status = Transaction.Status.PENDING
        tx.paid_at = None
    tx.save(update_fields=["status", "paid_at"])
    return _voltar(request)


@workspace_required
@require_POST
def transaction_delete(request: HttpRequest, pk: int) -> HttpResponse:
    tx = get_object_or_404(Transaction, pk=pk, workspace=request.workspace)
    label = tx.description
    tx.delete()
    messages.success(request, f'Lançamento "{label}" excluído.')
    return redirect("financeiro:lancamentos")


@workspace_required
@require_POST
def transaction_consolidate(request: HttpRequest, pk: int) -> HttpResponse:
    """Converte venda projetada em receita consolidada."""
    tx = get_object_or_404(Transaction, pk=pk, workspace=request.workspace)
    if tx.entry_kind != Transaction.EntryKind.PROJECTED_SALE:
        messages.error(request, "Só vendas projetadas podem ser consolidadas.")
        return _voltar(request)
    tx.entry_kind = Transaction.EntryKind.INCOME
    if tx.amount_cents < 0:
        tx.amount_cents = abs(tx.amount_cents)
    tx.save(update_fields=["entry_kind", "amount_cents"])
    messages.success(
        request,
        f'"{tx.description}" consolidada como receita.',
    )
    return _voltar(request)

