from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from funcionarios.utils import obter_funcionario

from . import planner_views
from .forms import AtividadeForm, AtividadeRapidaForm
from .models import AtividadeDiaria, PrioridadeAtividade, StatusAtividade
from .permissions import (
    pode_dirigir_atividades,
    pode_gerenciar_atividade,
    funcionarios_atribuiveis,
)
from .services import (
    agrupar_por_pessoa,
    agrupar_por_prioridade,
    agrupar_por_status,
    alterar_status,
    alternar_cronometro,
    atualizar_atividade,
    atividades_filtradas,
    criar_atividade,
    excluir_atividade,
    formatar_tempo,
    historico_planner,
    resumo_visivel,
)


def _parse_data(valor: str | None):
    if not valor:
        return timezone.localdate()
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def _redirect_lista(request, **extra):
    params = request.GET.copy()
    for key in ("org", "escopo", "data", "resp"):
        if key not in params and request.POST.get(key):
            params[key] = request.POST.get(key)
    for k, v in extra.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v
    qs = params.urlencode()
    base = reverse("atividades")
    return redirect(f"{base}?{qs}" if qs else base)


@login_required
def lista(request):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        messages.error(request, "É necessário ter um perfil de funcionário vinculado.")
        return redirect("home")

    pode_dirigir = pode_dirigir_atividades(funcionario)
    organizacao = (request.GET.get("org") or "status").strip()
    if organizacao not in ("status", "prioridade", "planner"):
        organizacao = "status"
    escopo = (request.GET.get("escopo") or "minhas").strip()
    if escopo not in ("minhas", "equipe") or not pode_dirigir:
        escopo = "minhas"
    dia = _parse_data(request.GET.get("data"))
    responsavel_id = None
    if escopo == "equipe" and request.GET.get("resp"):
        try:
            responsavel_id = int(request.GET.get("resp"))
        except (TypeError, ValueError):
            responsavel_id = None

    if organizacao == "planner" and request.method == "GET":
        return planner_views.planner(request, funcionario=funcionario, dia=dia)

    abrir_popup_tarefa = False
    if request.method == "POST":
        acao = request.POST.get("acao") or "criar"
        if acao == "criar_rapida":
            form_rapida = AtividadeRapidaForm(request.POST, ator=funcionario)
            if form_rapida.is_valid():
                criar_atividade(
                    funcionario,
                    titulo=form_rapida.cleaned_data["titulo"],
                    responsavel=form_rapida.cleaned_data.get("responsavel"),
                    status=form_rapida.cleaned_data.get("status")
                    or StatusAtividade.NAO_INICIADO,
                    prioridade=form_rapida.cleaned_data.get("prioridade")
                    or PrioridadeAtividade.MEDIA,
                    planejado_para=form_rapida.cleaned_data.get("planejado_para")
                    or dia,
                    data_vencimento=form_rapida.cleaned_data.get("data_vencimento"),
                    hora_inicio=form_rapida.cleaned_data.get("hora_inicio"),
                    hora_fim=form_rapida.cleaned_data.get("hora_fim"),
                )
                messages.success(request, "Tarefa adicionada.")
            else:
                erro = next(iter(form_rapida.errors.values()), ["Dados inválidos."])[0]
                messages.error(request, erro)
            return _redirect_lista(request)

        if acao == "criar":
            form = AtividadeForm(request.POST, ator=funcionario)
            if form.is_valid():
                criar_atividade(
                    funcionario,
                    titulo=form.cleaned_data["titulo"],
                    responsavel=form.cleaned_data.get("responsavel"),
                    status=form.cleaned_data.get("status")
                    or StatusAtividade.NAO_INICIADO,
                    prioridade=form.cleaned_data.get("prioridade")
                    or PrioridadeAtividade.MEDIA,
                    descricao=form.cleaned_data.get("descricao") or "",
                    planejado_para=form.cleaned_data.get("planejado_para") or dia,
                    data_vencimento=form.cleaned_data.get("data_vencimento"),
                    hora_inicio=form.cleaned_data.get("hora_inicio"),
                    hora_fim=form.cleaned_data.get("hora_fim"),
                )
                messages.success(request, "Tarefa criada.")
                return _redirect_lista(request)
            messages.error(request, "Revise os dados da tarefa.")
            abrir_popup_tarefa = True
        else:
            form = AtividadeForm(ator=funcionario, initial={"planejado_para": dia})
    else:
        form = AtividadeForm(ator=funcionario, initial={"planejado_para": dia})

    itens = atividades_filtradas(
        funcionario,
        escopo=escopo,
        responsavel_id=responsavel_id,
        dia=dia,
        organizacao=organizacao,
    )
    equipe = list(funcionarios_atribuiveis(funcionario))
    # Equipe (Todos): quadro por pessoa. Com filtro de 1 responsável, mantém status/prioridade.
    if escopo == "equipe" and not responsavel_id:
        grupos = agrupar_por_pessoa(itens, equipe)
        agrupamento = "pessoa"
    elif organizacao == "prioridade":
        grupos = agrupar_por_prioridade(itens)
        agrupamento = "prioridade"
    else:
        grupos = agrupar_por_status(itens)
        agrupamento = "status"

    hoje = timezone.localdate()
    for g in grupos:
        for item in g["itens"]:
            item.tempo_fmt = formatar_tempo(item.tempo_atual_segundos())
            item.atrasada = bool(
                item.data_vencimento
                and item.data_vencimento < hoje
                and item.status != StatusAtividade.REALIZADO
            )

    return render(
        request,
        "atividades/lista.html",
        {
            "form": form,
            "form_rapida": AtividadeRapidaForm(ator=funcionario),
            "grupos": grupos,
            "resumo": resumo_visivel(
                funcionario,
                escopo=escopo,
                responsavel_id=responsavel_id,
                dia=dia,
            ),
            "hoje": hoje,
            "dia": dia,
            "dia_anterior": dia - timedelta(days=1),
            "dia_seguinte": dia + timedelta(days=1),
            "organizacao": organizacao,
            "agrupamento": agrupamento,
            "escopo": escopo,
            "pode_dirigir": pode_dirigir,
            "eu": funcionario,
            "equipe": equipe,
            "responsavel_id": responsavel_id,
            "historico": historico_planner(funcionario) if organizacao == "planner" else [],
            "status_choices": StatusAtividade.choices,
            "prioridade_choices": PrioridadeAtividade.choices,
            "eh_hoje": dia == hoje,
            "abrir_popup_tarefa": abrir_popup_tarefa,
        },
    )


@login_required
@require_POST
def editar(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = get_object_or_404(
        AtividadeDiaria.objects.select_related("responsavel"), pk=pk
    )
    if not pode_gerenciar_atividade(funcionario, item):
        messages.error(request, "Sem permissão para editar esta tarefa.")
        return redirect("atividades")

    form = AtividadeForm(request.POST, instance=item, ator=funcionario)
    if form.is_valid():
        dest = form.cleaned_data.get("responsavel") or item.responsavel
        if not pode_dirigir_atividades(funcionario):
            dest = item.responsavel
        prio = form.cleaned_data.get("prioridade")
        quad = form.cleaned_data.get("quadrante")
        if prio and not quad:
            from .models import quadrante_por_prioridade

            quad = quadrante_por_prioridade(prio)
        atualizar_atividade(
            item,
            titulo=form.cleaned_data["titulo"],
            descricao=form.cleaned_data.get("descricao") or "",
            prioridade=prio,
            status=form.cleaned_data.get("status"),
            quadrante=quad,
            planejado_para=form.cleaned_data.get("planejado_para"),
            data_vencimento=form.cleaned_data.get("data_vencimento"),
            hora_inicio=form.cleaned_data.get("hora_inicio"),
            hora_fim=form.cleaned_data.get("hora_fim"),
            responsavel=dest,
        )
        messages.success(request, "Tarefa atualizada.")
    else:
        messages.error(request, "Não foi possível atualizar a tarefa.")
    return _redirect_lista(request)


@login_required
@require_POST
def excluir(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = get_object_or_404(AtividadeDiaria, pk=pk)
    if not pode_gerenciar_atividade(funcionario, item):
        messages.error(request, "Sem permissão para excluir esta tarefa.")
        return redirect("atividades")
    excluir_atividade(item)
    messages.success(request, "Tarefa removida.")
    return _redirect_lista(request)


@login_required
@require_POST
def mudar_status(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = get_object_or_404(AtividadeDiaria, pk=pk)
    if not pode_gerenciar_atividade(funcionario, item):
        messages.error(request, "Sem permissão.")
        return redirect("atividades")
    status = request.POST.get("status") or ""
    alterar_status(item, status)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "status": item.status})
    return _redirect_lista(request)


@login_required
@require_POST
def cronometro(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = get_object_or_404(AtividadeDiaria, pk=pk)
    if item.responsavel_id != funcionario.id and not pode_dirigir_atividades(
        funcionario
    ):
        messages.error(request, "Só o responsável pode usar o cronômetro.")
        return redirect("atividades")
    # Cronômetro só para o responsável (mesmo se gerente iniciar, conta no responsável)
    ator_timer = item.responsavel
    if item.responsavel_id != funcionario.id:
        # gerente só visualiza; não inicia timer de outro
        messages.error(request, "O cronômetro é pessoal do responsável.")
        return redirect("atividades")

    alternar_cronometro(item, ator_timer)
    item.refresh_from_db()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": True,
                "ativo": item.cronometro_ativo,
                "segundos": item.tempo_atual_segundos(),
                "texto": formatar_tempo(item.tempo_atual_segundos()),
                "inicio": item.cronometro_inicio.isoformat()
                if item.cronometro_inicio
                else None,
            }
        )
    return _redirect_lista(request)
