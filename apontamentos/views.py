from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from calendario.models import Demanda, StatusDemanda
from funcionarios.utils import obter_funcionario

from .forms import (
    MarcacaoPontoForm,
    SolicitacaoEdicaoMarcacaoForm,
    SolicitacaoExclusaoMarcacaoForm,
)
from .models import (
    MarcacaoPonto,
    SolicitacaoEdicaoMarcacao,
    StatusSolicitacao,
    TipoMarcacao,
    TipoSolicitacaoMarcacao,
)
from .permissions import pode_aprovar_edicoes_marcacao
from .services import (
    formatar_duracao,
    inicio_semana,
    jornada_em_andamento,
    limitar_ao_marco_zero,
    montar_dashboard,
    segundos_trabalhados,
)


def _exige_funcionario(request):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        messages.error(request, "É necessário ter um perfil de funcionário vinculado.")
        return None
    return funcionario


def _parse_periodo(request):
    hoje = timezone.localdate()
    padrao_inicio = inicio_semana(hoje)
    try:
        inicio = date.fromisoformat(
            request.GET.get("inicio", "") or padrao_inicio.isoformat()
        )
    except ValueError:
        inicio = padrao_inicio
    try:
        fim = date.fromisoformat(request.GET.get("fim", "") or hoje.isoformat())
    except ValueError:
        fim = hoje
    if fim < inicio:
        inicio, fim = fim, inicio
    # Não conta horas anteriores ao marco zero (semana de go-live)
    inicio = limitar_ao_marco_zero(inicio)
    if fim < inicio:
        fim = inicio
    return inicio, fim


@login_required
def apontamentos(request):
    funcionario = _exige_funcionario(request)
    if funcionario is None:
        return redirect("home")

    if request.method == "POST":
        demanda_id = request.POST.get("demanda_id")
        novo_status = request.POST.get("demanda_status")
        if demanda_id and novo_status in StatusDemanda.values:
            demanda = get_object_or_404(
                Demanda,
                pk=demanda_id,
                funcionario=funcionario,
                origem_day_off=True,
            )
            demanda.status = novo_status
            demanda.save(update_fields=["status", "atualizado_em"])
            messages.success(request, "Status da recuperação atualizado.")
            return redirect("apontamentos")

        tipo_rapido = request.POST.get("tipo_rapido")
        if tipo_rapido in TipoMarcacao.values:
            MarcacaoPonto.objects.create(
                funcionario=funcionario,
                tipo=tipo_rapido,
                data_hora=timezone.now(),
            )
            messages.success(
                request,
                f"Marcação registrada: {TipoMarcacao(tipo_rapido).label}.",
            )
            return redirect("apontamentos")

        form = MarcacaoPontoForm(request.POST)
        if form.is_valid():
            marcacao = form.save(commit=False)
            marcacao.funcionario = funcionario
            marcacao.save()
            messages.success(request, "Apontamento registrado.")
            return redirect("apontamentos")
    else:
        form = MarcacaoPontoForm()

    hoje = timezone.localdate()
    inicio, fim = _parse_periodo(request)

    marcacoes_periodo = list(
        MarcacaoPonto.objects.filter(
            funcionario=funcionario,
            data_hora__date__gte=inicio,
            data_hora__date__lte=fim,
        ).order_by("data_hora")
    )
    dashboard = montar_dashboard(marcacoes_periodo, inicio, fim, funcionario)

    marcacoes_hoje = MarcacaoPonto.objects.filter(
        funcionario=funcionario,
        data_hora__date=hoje,
    )
    marcacoes_hoje_list = list(marcacoes_hoje)
    segundos_hoje = segundos_trabalhados(marcacoes_hoje_list)

    pendentes_prefetch = Prefetch(
        "solicitacoes_edicao",
        queryset=SolicitacaoEdicaoMarcacao.objects.filter(
            status=StatusSolicitacao.PENDENTE
        ),
        to_attr="edicoes_pendentes",
    )
    log_qs = (
        MarcacaoPonto.objects.filter(
            funcionario=funcionario,
            data_hora__date__gte=inicio,
            data_hora__date__lte=fim,
        )
        .prefetch_related(pendentes_prefetch)
        .order_by("-data_hora")
    )
    pode_aprovar = pode_aprovar_edicoes_marcacao(request.user)
    log_marcacoes = []
    for m in log_qs:
        pendente = bool(getattr(m, "edicoes_pendentes", None))
        log_marcacoes.append(
            {
                "marcacao": m,
                "pendente": pendente,
                "edit_form": None
                if pendente
                else SolicitacaoEdicaoMarcacaoForm(marcacao=m, prefix=f"edit{m.pk}"),
                "delete_form": None
                if pendente or pode_aprovar
                else SolicitacaoExclusaoMarcacaoForm(
                    prefix=f"del{m.pk}",
                    exige_motivo=True,
                ),
            }
        )

    minhas_solicitacoes = (
        SolicitacaoEdicaoMarcacao.objects.filter(solicitado_por=funcionario)
        .select_related("marcacao")
        .order_by("-criado_em")[:15]
    )
    aprovacoes_pendentes = []
    if pode_aprovar:
        aprovacoes_pendentes = list(
            SolicitacaoEdicaoMarcacao.objects.filter(status=StatusSolicitacao.PENDENTE)
            .select_related("marcacao", "marcacao__funcionario", "solicitado_por")
            .order_by("criado_em")
        )

    recuperacoes = (
        Demanda.objects.filter(funcionario=funcionario, origem_day_off=True)
        .select_related("evento_origem")
        .order_by("data_prevista", "id")
    )
    horas_pendentes = recuperacoes.filter(
        status__in=[StatusDemanda.PENDENTE, StatusDemanda.EM_ANDAMENTO]
    ).aggregate(total=Sum("horas"))["total"] or Decimal("0")
    horas_concluidas = recuperacoes.filter(
        status=StatusDemanda.CONCLUIDA
    ).aggregate(total=Sum("horas"))["total"] or Decimal("0")

    return render(
        request,
        "apontamentos/apontamentos.html",
        {
            "form": form,
            "marcacoes_hoje": marcacoes_hoje,
            "log_marcacoes": log_marcacoes,
            "tipos": TipoMarcacao,
            "dashboard": dashboard,
            "inicio": inicio,
            "fim": fim,
            "horas_hoje": formatar_duracao(segundos_hoje),
            "em_andamento": jornada_em_andamento(marcacoes_hoje_list),
            "recuperacoes": recuperacoes,
            "horas_recuperar_pendentes": horas_pendentes,
            "horas_recuperar_concluidas": horas_concluidas,
            "status_recuperacao": StatusDemanda,
            "minhas_solicitacoes": minhas_solicitacoes,
            "pode_aprovar_edicoes": pode_aprovar,
            "aprovacoes_pendentes": aprovacoes_pendentes,
        },
    )


@login_required
def solicitar_edicao_marcacao(request, pk: int):
    funcionario = _exige_funcionario(request)
    if funcionario is None:
        return redirect("home")

    marcacao = get_object_or_404(MarcacaoPonto, pk=pk, funcionario=funcionario)
    if SolicitacaoEdicaoMarcacao.objects.filter(
        marcacao=marcacao, status=StatusSolicitacao.PENDENTE
    ).exists():
        messages.warning(request, "Já existe uma correção pendente para esta marcação.")
        return redirect("apontamentos")

    if request.method != "POST":
        return redirect("apontamentos")

    form = SolicitacaoEdicaoMarcacaoForm(
        request.POST,
        marcacao=marcacao,
        prefix=f"edit{marcacao.pk}",
    )
    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
        return redirect("apontamentos")

    solicitacao = form.save(commit=False)
    solicitacao.tipo_solicitacao = TipoSolicitacaoMarcacao.EDICAO
    solicitacao.marcacao = marcacao
    solicitacao.solicitado_por = funcionario
    solicitacao.tipo_original = marcacao.tipo
    solicitacao.data_hora_original = marcacao.data_hora
    solicitacao.observacao_original = marcacao.observacao

    # Rhuan (aprovador) corrige e aplica na hora
    if pode_aprovar_edicoes_marcacao(request.user):
        solicitacao.status = StatusSolicitacao.APROVADA
        solicitacao.revisado_por = request.user
        solicitacao.revisado_em = timezone.now()
        solicitacao.nota_revisao = "Aplicada automaticamente pelo aprovador."
        solicitacao.save()
        solicitacao.aplicar_se_aprovada()
        messages.success(request, "Marcação corrigida.")
    else:
        solicitacao.status = StatusSolicitacao.PENDENTE
        solicitacao.save()
        messages.success(
            request,
            "Correção enviada ao Rhuan para aprovação. A marcação atual permanece até a decisão.",
        )
    return redirect("apontamentos")


@login_required
def solicitar_exclusao_marcacao(request, pk: int):
    funcionario = _exige_funcionario(request)
    if funcionario is None:
        return redirect("home")

    marcacao = get_object_or_404(MarcacaoPonto, pk=pk, funcionario=funcionario)
    if SolicitacaoEdicaoMarcacao.objects.filter(
        marcacao=marcacao, status=StatusSolicitacao.PENDENTE
    ).exists():
        messages.warning(
            request,
            "Já existe uma solicitação pendente para esta marcação.",
        )
        return redirect("apontamentos")

    if request.method != "POST":
        return redirect("apontamentos")

    pode_aprovar = pode_aprovar_edicoes_marcacao(request.user)
    form = SolicitacaoExclusaoMarcacaoForm(
        request.POST,
        prefix=f"del{marcacao.pk}",
        exige_motivo=not pode_aprovar,
    )
    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
        return redirect("apontamentos")

    motivo = form.cleaned_data.get("motivo") or (
        "Exclusão direta pelo aprovador." if pode_aprovar else ""
    )
    solicitacao = SolicitacaoEdicaoMarcacao(
        tipo_solicitacao=TipoSolicitacaoMarcacao.EXCLUSAO,
        marcacao=marcacao,
        solicitado_por=funcionario,
        tipo_original=marcacao.tipo,
        data_hora_original=marcacao.data_hora,
        observacao_original=marcacao.observacao,
        tipo_proposto=marcacao.tipo,
        data_hora_proposta=marcacao.data_hora,
        observacao_proposta=marcacao.observacao,
        motivo=motivo,
    )

    if pode_aprovar:
        solicitacao.status = StatusSolicitacao.APROVADA
        solicitacao.revisado_por = request.user
        solicitacao.revisado_em = timezone.now()
        solicitacao.nota_revisao = "Exclusão aplicada automaticamente pelo aprovador."
        solicitacao.save()
        solicitacao.aplicar_se_aprovada()
        messages.success(request, "Marcação excluída.")
    else:
        solicitacao.status = StatusSolicitacao.PENDENTE
        solicitacao.save()
        messages.success(
            request,
            "Pedido de exclusão enviado ao Rhuan. A marcação permanece até a decisão.",
        )
    return redirect("apontamentos")


@login_required
def revisar_edicao_marcacao(request, pk: int):
    if not pode_aprovar_edicoes_marcacao(request.user):
        messages.error(request, "Somente o Rhuan pode aprovar ou recusar solicitações.")
        return redirect("apontamentos")

    solicitacao = get_object_or_404(
        SolicitacaoEdicaoMarcacao.objects.select_related("marcacao"),
        pk=pk,
        status=StatusSolicitacao.PENDENTE,
    )

    if request.method != "POST":
        return redirect("apontamentos")

    decisao = request.POST.get("decisao")
    nota = (request.POST.get("nota_revisao") or "").strip()
    eh_exclusao = solicitacao.is_exclusao

    if decisao == "aprovar":
        solicitacao.status = StatusSolicitacao.APROVADA
        solicitacao.revisado_por = request.user
        solicitacao.revisado_em = timezone.now()
        solicitacao.nota_revisao = nota
        solicitacao.save(
            update_fields=["status", "revisado_por", "revisado_em", "nota_revisao"]
        )
        solicitacao.aplicar_se_aprovada()
        if eh_exclusao:
            messages.success(request, "Exclusão aprovada. Marcação removida.")
        else:
            messages.success(request, "Correção aprovada. Marcação atualizada.")
    elif decisao == "recusar":
        solicitacao.status = StatusSolicitacao.RECUSADA
        solicitacao.revisado_por = request.user
        solicitacao.revisado_em = timezone.now()
        solicitacao.nota_revisao = nota or "Recusada — marcação original mantida."
        solicitacao.save(
            update_fields=["status", "revisado_por", "revisado_em", "nota_revisao"]
        )
        if eh_exclusao:
            messages.info(request, "Exclusão recusada. A marcação foi mantida.")
        else:
            messages.info(request, "Correção recusada. A marcação original foi mantida.")
    else:
        messages.error(request, "Decisão inválida.")

    return redirect("apontamentos")


@login_required
def ferias(request):
    return redirect("calendario")


@login_required
def day_off(request):
    return redirect("calendario")


@login_required
def resumo_horas(request):
    funcionario = _exige_funcionario(request)
    if funcionario is None:
        return redirect("home")

    inicio, fim = _parse_periodo(request)

    marcacoes = list(
        MarcacaoPonto.objects.filter(
            funcionario=funcionario,
            data_hora__date__gte=inicio,
            data_hora__date__lte=fim,
        ).order_by("data_hora")
    )

    por_dia: dict[date, list] = defaultdict(list)
    for m in marcacoes:
        por_dia[timezone.localtime(m.data_hora).date()].append(m)

    resumo = []
    total_segundos = 0
    for dia, itens in sorted(por_dia.items()):
        segundos = segundos_trabalhados(itens)
        total_segundos += segundos
        resumo.append(
            {
                "dia": dia,
                "marcacoes": itens,
                "horas": formatar_duracao(segundos),
            }
        )

    return render(
        request,
        "apontamentos/resumo_horas.html",
        {
            "inicio": inicio,
            "fim": fim,
            "resumo": resumo,
            "total_horas": formatar_duracao(total_segundos),
        },
    )
