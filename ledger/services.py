from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from ledger.models import InstallmentPurchase, Recurrence, Transaction


def split_installment_amounts(total_cents: int, num_installments: int) -> list[int]:
    if num_installments < 1:
        raise ValueError("num_installments deve ser >= 1")
    if total_cents <= 0:
        raise ValueError("total_cents deve ser > 0")
    base = total_cents // num_installments
    amounts = [base] * num_installments
    amounts[-1] = total_cents - base * (num_installments - 1)
    return amounts


def build_installment_schedule(
    total_cents: int, num_installments: int, first_due: date
) -> list[tuple[int, date, int]]:
    amounts = split_installment_amounts(total_cents, num_installments)
    dates = [first_due + relativedelta(months=i) for i in range(num_installments)]
    return [(i + 1, dates[i], amounts[i]) for i in range(num_installments)]


def create_installment_purchase(
    *,
    workspace,
    description: str,
    total_amount_cents: int,
    num_installments: int,
    first_due_date: date,
    competence_date: date,
    account,
    category,
    nature: str = InstallmentPurchase.Nature.PROFESSIONAL,
    project=None,
    reimbursable: bool = False,
    reimburse_to_entity=None,
    notes: str = "",
) -> InstallmentPurchase:
    purchase = InstallmentPurchase.objects.create(
        workspace=workspace,
        description=description,
        total_amount_cents=total_amount_cents,
        num_installments=num_installments,
        first_due_date=first_due_date,
        competence_date=competence_date,
        account=account,
        category=category,
        nature=nature,
        project=project,
        reimbursable=reimbursable,
        reimburse_to_entity=reimburse_to_entity,
        notes=notes,
    )
    for number, due, amount in build_installment_schedule(
        total_amount_cents, num_installments, first_due_date
    ):
        Transaction.objects.create(
            workspace=workspace,
            competence_date=competence_date,
            due_date=due,
            amount_cents=-amount,
            description=f"{description} ({number}/{num_installments})",
            category=category,
            account=account,
            status=Transaction.Status.PENDING,
            nature=nature,
            entry_kind=Transaction.EntryKind.VARIABLE_EXPENSE,
            reimbursable=reimbursable,
            reimburse_to_entity=reimburse_to_entity,
            project=project,
            notes=notes,
            installment_purchase=purchase,
            installment_number=number,
            installment_total=num_installments,
        )
    return purchase


def iter_recurrence_dates(
    start: date,
    periodicity: str,
    *,
    range_start: date,
    range_end: date,
    end_date: date | None = None,
) -> list[date]:
    delta = {
        Recurrence.Periodicity.MONTHLY: relativedelta(months=1),
        Recurrence.Periodicity.QUARTERLY: relativedelta(months=3),
        Recurrence.Periodicity.YEARLY: relativedelta(years=1),
    }[periodicity]
    hard_end = min(range_end, end_date) if end_date else range_end
    if start > hard_end:
        return []
    current = start
    guard = 0
    while current < range_start and current <= hard_end and guard < 10_000:
        current += delta
        guard += 1
    dates: list[date] = []
    while current <= hard_end and guard < 10_000:
        if current >= range_start:
            dates.append(current)
        current += delta
        guard += 1
    return dates


def expand_recurrence(
    recurrence: Recurrence, *, range_start: date, range_end: date
) -> list[dict]:
    if not recurrence.active:
        return []
    amount = abs(recurrence.amount_cents)
    if recurrence.category.kind == recurrence.category.Kind.EXPENSE:
        signed = -amount
    else:
        signed = amount
    desc = recurrence.description
    if recurrence.employee_id and recurrence.employee.name not in desc:
        desc = f"{desc} — {recurrence.employee.name}"
    return [
        {
            "recurrence_id": recurrence.id,
            "due_date": d,
            "amount_cents": signed,
            "description": desc,
            "account_id": recurrence.account_id,
            "category_id": recurrence.category_id,
            "nature": recurrence.nature,
            "project_id": recurrence.project_id,
            "entry_kind": recurrence.entry_kind,
            "employee_id": recurrence.employee_id,
        }
        for d in iter_recurrence_dates(
            recurrence.start_date,
            recurrence.periodicity,
            range_start=range_start,
            range_end=range_end,
            end_date=recurrence.end_date,
        )
    ]


def materialize_recurrence(
    recurrence: Recurrence, *, range_start: date, range_end: date
) -> list[Transaction]:
    existing = set(
        Transaction.objects.filter(recurrence=recurrence).values_list("due_date", flat=True)
    )
    created: list[Transaction] = []
    for occ in expand_recurrence(recurrence, range_start=range_start, range_end=range_end):
        if occ["due_date"] in existing:
            continue
        created.append(
            Transaction.objects.create(
                workspace=recurrence.workspace,
                competence_date=occ["due_date"],
                due_date=occ["due_date"],
                amount_cents=occ["amount_cents"],
                description=occ["description"],
                category_id=occ["category_id"],
                account_id=occ["account_id"],
                status=Transaction.Status.PENDING,
                nature=occ["nature"],
                project_id=occ["project_id"],
                entry_kind=occ["entry_kind"],
                employee_id=occ["employee_id"],
                recurrence=recurrence,
            )
        )
    return created


def create_entry_with_optional_recurrence(
    *,
    workspace,
    entry_kind: str,
    description: str,
    amount_cents: int,
    account,
    category,
    nature: str,
    status: str,
    competence_date,
    due_date,
    project=None,
    employee=None,
    notes: str = "",
    reimbursable: bool = False,
    reimburse_to_entity=None,
    is_recurring: bool = False,
    periodicity: str = Recurrence.Periodicity.MONTHLY,
    recurrence_start=None,
    recurrence_end=None,
) -> tuple[Recurrence | None, list[Transaction]]:
    """Cria lançamento único ou recorrência materializada no período."""
    from dateutil.relativedelta import relativedelta

    from ledger.models import EntryKind

    signed = abs(amount_cents)
    if entry_kind not in {EntryKind.INCOME, EntryKind.PROJECTED_SALE}:
        signed = -signed

    desc = description
    if employee and employee.name not in description:
        desc = f"{description} — {employee.name}"

    if not is_recurring:
        tx = Transaction.objects.create(
            workspace=workspace,
            competence_date=competence_date,
            due_date=due_date,
            amount_cents=signed,
            description=desc,
            entry_kind=entry_kind,
            category=category,
            account=account,
            status=status,
            nature=nature,
            project=project,
            employee=employee,
            notes=notes,
            reimbursable=reimbursable,
            reimburse_to_entity=reimburse_to_entity,
            paid_at=competence_date if status == Transaction.Status.PAID else None,
        )
        return None, [tx]

    start = recurrence_start or due_date or competence_date
    end = recurrence_end or (start + relativedelta(months=11))
    rec = Recurrence.objects.create(
        workspace=workspace,
        description=desc,
        amount_cents=abs(amount_cents),
        periodicity=periodicity,
        start_date=start,
        end_date=recurrence_end,
        account=account,
        category=category,
        nature=nature,
        entry_kind=entry_kind,
        employee=employee,
        project=project,
        active=True,
        notes=notes,
    )
    created = materialize_recurrence(rec, range_start=start, range_end=end)
    return rec, created


def monthly_depreciation_cents(
    acquisition_value_cents: int, residual_value_cents: int, useful_life_months: int
) -> int:
    if useful_life_months <= 0:
        raise ValueError("useful_life_months deve ser > 0")
    if acquisition_value_cents < residual_value_cents:
        raise ValueError("aquisição < residual")
    return (acquisition_value_cents - residual_value_cents) // useful_life_months


def months_between(start: date, end: date) -> int:
    if end < start:
        return 0
    rd = relativedelta(end, start)
    return rd.years * 12 + rd.months


def depreciation_as_of(equipment, as_of: date) -> dict:
    monthly = monthly_depreciation_cents(
        equipment.acquisition_value_cents,
        equipment.residual_value_cents,
        equipment.useful_life_months,
    )
    elapsed = min(
        months_between(equipment.acquisition_date, as_of),
        equipment.useful_life_months,
    )
    max_dep = equipment.acquisition_value_cents - equipment.residual_value_cents
    accumulated = min(monthly * elapsed, max_dep)
    book = max(equipment.acquisition_value_cents - accumulated, equipment.residual_value_cents)
    return {
        "monthly_cents": monthly,
        "months_elapsed": elapsed,
        "accumulated_cents": accumulated,
        "book_value_cents": book,
        "fully_depreciated": elapsed >= equipment.useful_life_months,
    }


DEFAULT_COMPANY_TAX_BPS = 1700  # 17%


def tax_from_revenue_cents(revenue_cents: int, rate_bps: int = DEFAULT_COMPANY_TAX_BPS) -> int:
    """Projeção de imposto = faturamento × alíquota efetiva (basis points)."""
    if revenue_cents <= 0 or rate_bps <= 0:
        return 0
    return (revenue_cents * rate_bps) // 10_000


def project_entity_tax(
    *,
    revenue_cents: int,
    taxes_booked_cents: int,
    rate_bps: int = DEFAULT_COMPANY_TAX_BPS,
) -> dict:
    """Compara imposto projetado pelo faturamento vs impostos já lançados."""
    projected = tax_from_revenue_cents(revenue_cents, rate_bps)
    booked = abs(taxes_booked_cents)
    return {
        "revenue_cents": revenue_cents,
        "rate_bps": rate_bps,
        "rate_percent": rate_bps / 100,
        "projected_tax_cents": projected,
        "booked_tax_cents": booked,
        "gap_cents": projected - booked,
    }


def mark_travel_reimbursed(request) -> "Transaction":
    """Gera receita de reembolso na conta que adiantou e fecha a solicitação."""
    from django.utils import timezone

    from ledger.models import Category, Transaction, TravelReimbursementRequest

    if request.status == TravelReimbursementRequest.Status.REIMBURSED:
        raise ValueError("Solicitação já reembolsada")
    if request.status not in {
        TravelReimbursementRequest.Status.APPROVED,
        TravelReimbursementRequest.Status.SUBMITTED,
    }:
        raise ValueError("Só é possível reembolsar solicitações enviadas ou aprovadas")

    total = request.total_cents
    if total <= 0:
        raise ValueError("Solicitação sem valores")

    category = (
        Category.objects.for_workspace(request.workspace)
        .filter(kind=Category.Kind.INCOME, name="Reembolsos recebidos")
        .first()
    )
    if category is None:
        raise ValueError("Categoria 'Reembolsos recebidos' não encontrada")

    payer = request.bill_to_label
    tx = Transaction.objects.create(
        workspace=request.workspace,
        competence_date=timezone.localdate(),
        due_date=timezone.localdate(),
        amount_cents=total,
        description=f"Reembolso viagem — {request.title} ({payer})",
        entry_kind=Transaction.EntryKind.INCOME,
        category=category,
        account=request.advance_account,
        status=Transaction.Status.PAID,
        nature=Transaction.Nature.PROFESSIONAL,
        notes=f"Solicitação #{request.pk} · {request.destination}",
        paid_at=timezone.localdate(),
    )
    request.status = TravelReimbursementRequest.Status.REIMBURSED
    request.reimbursed_at = timezone.now()
    request.reimbursement_transaction = tx
    request.save(
        update_fields=[
            "status",
            "reimbursed_at",
            "reimbursement_transaction",
        ]
    )
    return tx

