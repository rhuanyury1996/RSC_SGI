from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from funcionarios.models import Funcionario
from funcionarios.utils import obter_funcionario

from .models import (
    COPOS_AGUA_META,
    HABITOS_PADRAO,
    ML_POR_COPO,
    AtividadeDiaria,
    MetaFoco,
    PrioridadeAtividade,
    QuadranteEisenhower,
    StatusAtividade,
)
from .permissions import pode_dirigir_atividades
from .services import (
    adicionar_meta,
    agenda_por_hora,
    agua_copos_ui,
    alterar_status,
    alternar_habito,
    alternar_meta,
    criar_atividade,
    definir_agua,
    eventos_calendario_do_dia,
    formatar_tempo,
    matriz_eisenhower,
    metricas_planner,
    obter_ou_criar_dia,
    semana_habitos,
)


def _parse_data(valor: str | None):
    if not valor:
        return timezone.localdate()
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def _parse_hora(valor: str | None):
    if not valor or not str(valor).strip():
        return None
    raw = str(valor).strip()
    try:
        return datetime.strptime(raw[:5], "%H:%M").time()
    except ValueError:
        try:
            return datetime.strptime(raw, "%H:%M:%S").time()
        except ValueError:
            return None


def _resolver_alvo(request):
    """Retorna (eu, alvo, resp_id). Chefia pode ver planner de outro via ?resp=."""
    eu = obter_funcionario(request)
    if eu is None:
        return None, None, None
    if "resp" in request.GET:
        raw = (request.GET.get("resp") or "").strip()
    elif "resp" in request.POST:
        raw = (request.POST.get("resp") or "").strip()
    else:
        raw = (request.session.get("planner_resp") or "").strip()
    if raw and pode_dirigir_atividades(eu):
        try:
            alvo = Funcionario.objects.get(pk=int(raw), ativo=True)
            request.session["planner_resp"] = str(alvo.pk)
            return eu, alvo, alvo.pk
        except (TypeError, ValueError, Funcionario.DoesNotExist):
            pass
    request.session.pop("planner_resp", None)
    return eu, eu, None


def _redirect_planner(request, dia):
    _, _, resp_id = _resolver_alvo(request)
    qs = f"org=planner&data={dia.isoformat()}"
    if resp_id:
        qs += f"&resp={resp_id}"
    return redirect(f"{reverse('atividades')}?{qs}")


@login_required
def planner(request, *, funcionario, dia):
    eu, alvo, resp_id = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    # funcionario = quem está logado (compat); alvo = de quem é o planner
    if alvo is None:
        alvo = funcionario

    pode_dirigir = pode_dirigir_atividades(eu)
    dia_obj = obter_ou_criar_dia(alvo, dia)
    itens_qs = (
        AtividadeDiaria.objects.filter(responsavel=alvo, planejado_para=dia)
        .select_related("responsavel")
        .order_by(F("hora_inicio").asc(nulls_last=True), "ordem", "-criado_em")
    )
    itens = list(itens_qs)
    for item in itens:
        item.tempo_fmt = formatar_tempo(item.tempo_atual_segundos())

    eventos = eventos_calendario_do_dia(alvo, dia)
    checklist = itens
    metricas = metricas_planner(alvo, dia, itens)
    habitos_labels = dict(HABITOS_PADRAO)
    equipe = []
    if pode_dirigir:
        equipe = list(
            Funcionario.objects.filter(ativo=True).order_by("nome", "sobrenome")
        )

    return render(
        request,
        "atividades/planner.html",
        {
            "eu": eu,
            "alvo": alvo,
            "eh_meu_planner": alvo.pk == eu.pk,
            "pode_dirigir": pode_dirigir,
            "equipe": equipe,
            "resp_id": resp_id,
            "dia": dia,
            "hoje": timezone.localdate(),
            "eh_hoje": dia == timezone.localdate(),
            "dia_anterior": dia - timedelta(days=1),
            "dia_seguinte": dia + timedelta(days=1),
            "organizacao": "planner",
            "escopo": "minhas",
            "dia_planner": dia_obj,
            "metricas": metricas,
            "matriz": matriz_eisenhower(itens),
            "checklist": checklist,
            "agenda_horas": agenda_por_hora(itens, eventos=eventos),
            "agua_copos": agua_copos_ui(dia_obj.agua_copos),
            "agua_ml": dia_obj.agua_ml,
            "agua_meta_ml": dia_obj.agua_meta_ml,
            "agua_meta_copos": COPOS_AGUA_META,
            "ml_por_copo": ML_POR_COPO,
            "metas": list(dia_obj.metas.all()),
            "habitos_semana": semana_habitos(alvo, dia),
            "habitos_labels": habitos_labels,
            "habitos_hoje": [
                {
                    "chave": h.chave,
                    "nome": habitos_labels.get(h.chave, h.chave),
                    "feito": h.feito,
                }
                for h in dia_obj.habitos.all()
            ],
            "status_realizado": StatusAtividade.REALIZADO,
        },
    )


@login_required
@require_POST
def agua(request):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    dia = _parse_data(request.POST.get("data"))
    dia_obj = obter_ou_criar_dia(alvo, dia)
    try:
        copos = int(request.POST.get("copos") or 0)
    except (TypeError, ValueError):
        copos = 0
    definir_agua(dia_obj, copos)
    return _redirect_planner(request, dia)


@login_required
@require_POST
def habito(request):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    dia = _parse_data(request.POST.get("data"))
    voltar = _parse_data(request.POST.get("voltar") or request.POST.get("data"))
    chave = (request.POST.get("chave") or "").strip()
    if chave:
        dia_obj = obter_ou_criar_dia(alvo, dia)
        alternar_habito(dia_obj, chave)
    return _redirect_planner(request, voltar)


@login_required
@require_POST
def meta_add(request):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    dia = _parse_data(request.POST.get("data"))
    texto = (request.POST.get("texto") or "").strip()
    if texto:
        dia_obj = obter_ou_criar_dia(alvo, dia)
        adicionar_meta(dia_obj, texto)
        messages.success(request, "Meta adicionada.")
    return _redirect_planner(request, dia)


@login_required
@require_POST
def meta_toggle(request, pk: int):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    meta = get_object_or_404(MetaFoco, pk=pk, dia__funcionario=alvo)
    alternar_meta(meta)
    return _redirect_planner(request, meta.dia.data)


@login_required
@require_POST
def checklist_toggle(request, pk: int):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    item = get_object_or_404(AtividadeDiaria, pk=pk, responsavel=alvo)
    novo = (
        StatusAtividade.NAO_INICIADO
        if item.status == StatusAtividade.REALIZADO
        else StatusAtividade.REALIZADO
    )
    alterar_status(item, novo)
    dia = item.planejado_para or timezone.localdate()
    return _redirect_planner(request, dia)


@login_required
@require_POST
def planner_nota(request):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    dia = _parse_data(request.POST.get("data"))
    dia_obj = obter_ou_criar_dia(alvo, dia)
    origem = (request.POST.get("origem") or "").strip()
    campos = ["atualizado_em"]
    if origem in ("", "notas") and "notas" in request.POST:
        dia_obj.notas = (request.POST.get("notas") or "").strip()
        campos.append("notas")
    if origem in ("", "citacao") and "citacao" in request.POST:
        dia_obj.citacao = (request.POST.get("citacao") or "").strip()[:280]
        campos.append("citacao")
    if origem in ("", "pomodoro") and "pomodoros" in request.POST:
        try:
            dia_obj.pomodoros = max(0, min(12, int(request.POST.get("pomodoros") or 0)))
            campos.append("pomodoros")
        except (TypeError, ValueError):
            pass
    dia_obj.save(update_fields=list(dict.fromkeys(campos)))
    messages.success(request, "Planner atualizado.")
    return _redirect_planner(request, dia)


@login_required
@require_POST
def mudar_quadrante(request, pk: int):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    item = get_object_or_404(AtividadeDiaria, pk=pk, responsavel=alvo)
    ordem = [
        QuadranteEisenhower.FAZER,
        QuadranteEisenhower.AGENDAR,
        QuadranteEisenhower.DELEGAR,
        QuadranteEisenhower.ELIMINAR,
    ]
    atual = item.quadrante or QuadranteEisenhower.AGENDAR
    try:
        idx = ordem.index(atual)
    except ValueError:
        idx = 0
    item.quadrante = ordem[(idx + 1) % len(ordem)]
    item.save(update_fields=["quadrante", "atualizado_em"])
    dia = item.planejado_para or _parse_data(request.POST.get("data"))
    return _redirect_planner(request, dia)


@login_required
@require_POST
def planner_tarefa(request):
    eu, alvo, _ = _resolver_alvo(request)
    if eu is None:
        return redirect("home")
    dia = _parse_data(request.POST.get("data"))
    titulo = (request.POST.get("titulo") or "").strip()
    if titulo:
        prio = request.POST.get("prioridade") or PrioridadeAtividade.MEDIA
        if prio not in PrioridadeAtividade.values:
            prio = PrioridadeAtividade.MEDIA
        item = criar_atividade(
            eu,
            titulo=titulo,
            planejado_para=dia,
            responsavel=alvo,
            prioridade=prio,
            hora_inicio=_parse_hora(request.POST.get("hora_inicio")),
            hora_fim=_parse_hora(request.POST.get("hora_fim")),
        )
        quad = request.POST.get("quadrante") or ""
        if quad in QuadranteEisenhower.values and item.quadrante != quad:
            item.quadrante = quad
            item.save(update_fields=["quadrante", "atualizado_em"])
        messages.success(request, "Tarefa adicionada ao dia.")
    return _redirect_planner(request, dia)
