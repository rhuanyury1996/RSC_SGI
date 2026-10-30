from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from funcionarios.utils import obter_funcionario

from . import planner_views
from .forms import AtividadeForm, AtividadeRapidaForm, queryset_clientes_rsc
from .models import (
    AtividadeDiaria,
    PrioridadeAtividade,
    QuadranteEisenhower,
    StatusAtividade,
    TipoEventoAtividade,
    aviso_quadrante,
)
from .permissions import (
    pode_alterar_status,
    pode_comentar_atividade,
    pode_dirigir_atividades,
    pode_gerenciar_atividade,
    funcionarios_para_equipe,
)
from .services import (
    agrupar_por_pessoa,
    agrupar_por_prioridade,
    agrupar_por_status,
    alterar_status,
    alternar_cronometro,
    atualizar_atividade,
    atividades_filtradas,
    aviso_sobreposicao,
    criar_atividade,
    excluir_atividade,
    formatar_tempo,
    historico_planner,
    montar_arvore_atividades,
    registrar_evento,
    restaurar_atividade,
    resumo_visivel,
)


def _parse_data(valor: str | None):
    if not valor:
        return timezone.localdate()
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def _quer_json(request) -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept") or ""
    return "application/json" in accept


def _negar(request, mensagem: str, status: int = 403):
    if _quer_json(request):
        return JsonResponse({"ok": False, "erro": mensagem}, status=status)
    return HttpResponse(mensagem, status=status, content_type="text/plain; charset=utf-8")


def _atividade_ativa(pk: int) -> AtividadeDiaria:
    return get_object_or_404(
        AtividadeDiaria.objects.ativas().select_related("responsavel", "cliente_rsc"),
        pk=pk,
    )


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
    if organizacao not in ("status", "prioridade", "planner", "quadro"):
        organizacao = "status"
    escopo = (request.GET.get("escopo") or "equipe").strip()
    if escopo not in ("minhas", "equipe"):
        escopo = "equipe"
    if request.GET.get("minhas") == "1":
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
                criada = criar_atividade(
                    funcionario,
                    titulo=form_rapida.cleaned_data["titulo"],
                    responsavel=form_rapida.cleaned_data.get("responsavel"),
                    status=form_rapida.cleaned_data.get("status")
                    or StatusAtividade.NAO_INICIADO,
                    prioridade=form_rapida.cleaned_data.get("prioridade")
                    or PrioridadeAtividade.MEDIA,
                    cliente_rsc=form_rapida.cleaned_data.get("cliente_rsc"),
                    planejado_para=form_rapida.cleaned_data.get("planejado_para")
                    or dia,
                    data_vencimento=form_rapida.cleaned_data.get("data_vencimento"),
                    hora_inicio=form_rapida.cleaned_data.get("hora_inicio"),
                    hora_fim=form_rapida.cleaned_data.get("hora_fim"),
                )
                aviso = aviso_sobreposicao(
                    criada.responsavel,
                    criada.planejado_para,
                    criada.hora_inicio,
                    criada.hora_fim,
                    ignorar_pk=criada.pk,
                )
                if aviso:
                    messages.warning(request, aviso)
                messages.success(request, "Tarefa adicionada.")
            else:
                erro = next(iter(form_rapida.errors.values()), ["Dados inválidos."])[0]
                messages.error(request, erro)
            return _redirect_lista(request)

        if acao == "criar":
            form = AtividadeForm(request.POST, ator=funcionario)
            if form.is_valid():
                criada = criar_atividade(
                    funcionario,
                    titulo=form.cleaned_data["titulo"],
                    responsavel=form.cleaned_data.get("responsavel"),
                    participantes=form.cleaned_data.get("participantes"),
                    status=form.cleaned_data.get("status")
                    or StatusAtividade.NAO_INICIADO,
                    prioridade=form.cleaned_data.get("prioridade")
                    or PrioridadeAtividade.MEDIA,
                    quadrante=form.cleaned_data.get("quadrante")
                    or QuadranteEisenhower.AGENDAR,
                    descricao=form.cleaned_data.get("descricao") or "",
                    cliente_rsc=form.cleaned_data.get("cliente_rsc"),
                    planejado_para=form.cleaned_data.get("planejado_para") or dia,
                    data_vencimento=form.cleaned_data.get("data_vencimento"),
                    hora_inicio=form.cleaned_data.get("hora_inicio"),
                    hora_fim=form.cleaned_data.get("hora_fim"),
                )
                if getattr(form, "aviso", ""):
                    messages.warning(request, form.aviso)
                aviso = aviso_sobreposicao(
                    criada.responsavel,
                    criada.planejado_para,
                    criada.hora_inicio,
                    criada.hora_fim,
                    ignorar_pk=criada.pk,
                )
                if aviso:
                    messages.warning(request, aviso)
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
    equipe = list(funcionarios_para_equipe(funcionario))
    agrupamento_pedido = (request.GET.get("agrupar") or "").strip()
    if agrupamento_pedido == "pessoa":
        grupos = agrupar_por_pessoa(itens, equipe)
        agrupamento = "pessoa"
    elif organizacao == "prioridade" or agrupamento_pedido == "prioridade":
        grupos = agrupar_por_prioridade(itens)
        agrupamento = "prioridade"
    else:
        grupos = agrupar_por_status(itens)
        agrupamento = "status"

    hoje = timezone.localdate()

    def _anotar(item):
        item.tempo_fmt = formatar_tempo(item.tempo_atual_segundos())
        item.atrasada_desde = item.data_atraso(hoje)
        item.atrasada = item.atrasada_desde is not None
        for filho in getattr(item, "filhos", []) or []:
            _anotar(filho)

    for g in grupos:
        g["itens"] = montar_arvore_atividades(g["itens"])
        for item in g["itens"]:
            _anotar(item)

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
            "clientes_rsc": queryset_clientes_rsc(),
            "equipe_opcoes": list(funcionarios_para_equipe(funcionario)),
            "eh_hoje": dia == hoje,
            "abrir_popup_tarefa": abrir_popup_tarefa,
            "desfazer_id": request.GET.get("desfazer") or "",
        },
    )


@login_required
@require_POST
def editar(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = _atividade_ativa(pk)
    if not pode_gerenciar_atividade(funcionario, item):
        return _negar(request, "Sem permissão para editar esta tarefa.")

    form = AtividadeForm(request.POST, instance=item, ator=funcionario)
    if form.is_valid():
        dest = form.cleaned_data.get("responsavel") or item.responsavel
        if not pode_dirigir_atividades(funcionario):
            dest = item.responsavel
        prio = form.cleaned_data.get("prioridade")
        quad = form.cleaned_data.get("quadrante") or item.quadrante
        novo_status = form.cleaned_data.get("status")
        if novo_status and novo_status != item.status:
            alterar_status(item, novo_status, autor=funcionario)
            item.refresh_from_db()
        atualizar_atividade(
            item,
            titulo=form.cleaned_data["titulo"],
            descricao=form.cleaned_data.get("descricao") or "",
            cliente_rsc=form.cleaned_data.get("cliente_rsc"),
            prioridade=prio,
            quadrante=quad,
            planejado_para=form.cleaned_data.get("planejado_para"),
            data_vencimento=form.cleaned_data.get("data_vencimento"),
            hora_inicio=form.cleaned_data.get("hora_inicio"),
            hora_fim=form.cleaned_data.get("hora_fim"),
            responsavel=dest,
            participantes=form.cleaned_data.get("participantes"),
        )
        registrar_evento(
            item,
            funcionario,
            TipoEventoAtividade.EDICAO,
            texto="Atualizou a tarefa.",
        )
        if getattr(form, "aviso", ""):
            messages.warning(request, form.aviso)
        aviso = aviso_quadrante(prio or "", quad or "")
        if aviso and aviso != getattr(form, "aviso", ""):
            messages.warning(request, aviso)
        aviso_hora = aviso_sobreposicao(
            dest,
            form.cleaned_data.get("planejado_para"),
            form.cleaned_data.get("hora_inicio"),
            form.cleaned_data.get("hora_fim"),
            ignorar_pk=item.pk,
        )
        if aviso_hora:
            messages.warning(request, aviso_hora)
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
    item = _atividade_ativa(pk)
    if not pode_gerenciar_atividade(funcionario, item):
        return _negar(request, "Sem permissão para excluir esta tarefa.")
    excluir_atividade(item, funcionario)
    messages.success(request, "Tarefa removida.")
    return _redirect_lista(request, desfazer=item.pk)


@login_required
@require_POST
def criar_subtarefa(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    pai = get_object_or_404(
        AtividadeDiaria.objects.ativas().prefetch_related("participantes"), pk=pk
    )
    if pai.eh_subtarefa:
        messages.error(request, "Não é possível criar subtarefa de outra subtarefa.")
        return _redirect_lista(request)
    if not pode_gerenciar_atividade(funcionario, pai):
        return _negar(request, "Sem permissão para criar subtarefa.")

    titulo = (request.POST.get("titulo") or "").strip()
    if not titulo:
        messages.error(request, "Informe o título da subtarefa.")
        return _redirect_lista(request)

    resp_id = request.POST.get("responsavel")
    responsavel = None
    if resp_id:
        responsavel = next(
            (f for f in funcionarios_para_equipe(funcionario) if str(f.pk) == str(resp_id)),
            None,
        )
    criar_atividade(
        funcionario,
        titulo=titulo,
        responsavel=responsavel or funcionario,
        atividade_pai=pai,
        status=StatusAtividade.NAO_INICIADO,
        prioridade=pai.prioridade,
        cliente_rsc=pai.cliente_rsc,
        planejado_para=pai.planejado_para,
    )
    messages.success(request, "Subtarefa criada.")
    return _redirect_lista(request)


@login_required
@require_POST
def mudar_status(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = _atividade_ativa(pk)
    if not pode_alterar_status(funcionario, item):
        return _negar(request, "Sem permissão para mudar o status desta tarefa.")
    status = request.POST.get("status") or ""
    if status not in StatusAtividade.values:
        return _negar(request, "Status inválido.", status=400)
    alterar_status(item, status, autor=funcionario)
    item.refresh_from_db()
    if _quer_json(request):
        return JsonResponse(
            {
                "ok": True,
                "status": item.status,
                "label": item.get_status_display(),
                "cronometro_ativo": item.cronometro_ativo,
                "texto": formatar_tempo(item.tempo_atual_segundos()),
            }
        )
    return _redirect_lista(request)


@login_required
@require_POST
def cronometro(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = get_object_or_404(
        AtividadeDiaria.objects.ativas().prefetch_related("participantes"), pk=pk
    )
    if not (
        pode_gerenciar_atividade(funcionario, item)
        or item.faz_parte_da_equipe(funcionario)
    ):
        return _negar(
            request, "Só quem faz parte da equipe da tarefa pode usar o cronômetro."
        )
    if item.status == StatusAtividade.REALIZADO and not item.cronometro_inicio:
        return _negar(
            request,
            "Não é possível iniciar o timer de uma tarefa realizada.",
            status=400,
        )

    alternar_cronometro(item, funcionario)
    item.refresh_from_db()
    if _quer_json(request):
        return JsonResponse(
            {
                "ok": True,
                "pk": item.pk,
                "titulo": item.titulo,
                "ativo": item.cronometro_ativo,
                "segundos": item.tempo_atual_segundos(),
                "acumulado": int(item.tempo_acumulado_segundos or 0),
                "texto": formatar_tempo(item.tempo_atual_segundos()),
                "inicio": item.cronometro_inicio.isoformat()
                if item.cronometro_inicio
                else None,
            }
        )
    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return _redirect_lista(request)


@login_required
@require_POST
def restaurar(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = get_object_or_404(AtividadeDiaria, pk=pk, deletado_em__isnull=False)
    if not pode_gerenciar_atividade(funcionario, item):
        return _negar(request, "Sem permissão para restaurar esta tarefa.")
    restaurar_atividade(item, funcionario)
    messages.success(request, "Exclusão desfeita.")
    if _quer_json(request):
        return JsonResponse({"ok": True, "pk": item.pk})
    return _redirect_lista(request, desfazer=None)


@login_required
@require_POST
def comentar(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return redirect("home")
    item = _atividade_ativa(pk)
    if not pode_comentar_atividade(funcionario, item):
        return _negar(request, "Sem permissão para comentar.")
    texto = (request.POST.get("texto") or "").strip()
    if not texto:
        return _negar(request, "Escreva um comentário.", status=400)
    evento = registrar_evento(
        item,
        funcionario,
        TipoEventoAtividade.COMENTARIO,
        texto=texto,
    )
    if _quer_json(request):
        return JsonResponse(
            {
                "ok": True,
                "id": evento.pk,
                "texto": evento.texto,
                "autor": funcionario.nome_completo,
                "quando": timezone.localtime(evento.criado_em).strftime("%d/%m %H:%M"),
            }
        )
    messages.success(request, "Comentário registrado.")
    return _redirect_lista(request)
