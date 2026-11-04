from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from funcionarios.models import Funcionario
from funcionarios.utils import obter_funcionario

from . import planner_views
from .forms import AtividadeForm, AtividadeRapidaForm, queryset_clientes_rsc
from .models import (
    STATUS_CONCLUIDOS,
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
    alterar_status,
    alternar_cronometro,
    atualizar_atividade,
    aviso_sobreposicao,
    criar_atividade,
    definir_participantes,
    excluir_atividade,
    queryset_visivel,
    registrar_evento,
    relogio_para,
    reordenar_atividades,
    restaurar_atividade,
    serializar_atividade,
    serializar_pessoa,
    tarefas_para_visualizacoes,
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


VISOES = ("lista", "quadro", "gantt", "mapa")


def _tarefa_json(item: AtividadeDiaria, funcionario) -> dict:
    """Recarrega com os prefetches usados pelas visualizações."""
    fresco = queryset_visivel(funcionario, escopo="equipe").filter(pk=item.pk).first()
    return serializar_atividade(fresco or item, funcionario)


def _criar_rapida(request, funcionario, dia):
    form_rapida = AtividadeRapidaForm(request.POST, ator=funcionario)
    if not form_rapida.is_valid():
        erro = next(iter(form_rapida.errors.values()), ["Dados inválidos."])[0]
        if _quer_json(request):
            return JsonResponse({"ok": False, "erro": str(erro)}, status=400)
        messages.error(request, erro)
        return _redirect_lista(request)
    dados = form_rapida.cleaned_data
    vencimento = dados.get("data_vencimento")
    planejado = dados.get("planejado_para") or dia
    if vencimento and vencimento < planejado:
        planejado = vencimento
    criada = criar_atividade(
        funcionario,
        titulo=dados["titulo"],
        responsavel=dados.get("responsavel"),
        status=dados.get("status") or StatusAtividade.NAO_INICIADO,
        prioridade=dados.get("prioridade") or PrioridadeAtividade.MEDIA,
        cliente_rsc=dados.get("cliente_rsc"),
        planejado_para=planejado,
        data_vencimento=vencimento,
        hora_inicio=dados.get("hora_inicio"),
        hora_fim=dados.get("hora_fim"),
    )
    aviso = aviso_sobreposicao(
        criada.responsavel,
        criada.planejado_para,
        criada.hora_inicio,
        criada.hora_fim,
        ignorar_pk=criada.pk,
    )
    if _quer_json(request):
        return JsonResponse(
            {"ok": True, "aviso": aviso, "tarefa": _tarefa_json(criada, funcionario)}
        )
    if aviso:
        messages.warning(request, aviso)
    messages.success(request, "Tarefa adicionada.")
    return _redirect_lista(request)


@login_required
def lista(request):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        messages.error(request, "É necessário ter um perfil de funcionário vinculado.")
        return redirect("home")

    organizacao = (request.GET.get("org") or "lista").strip()
    if organizacao == "status":
        organizacao = "lista"
    elif organizacao == "prioridade":
        organizacao = "quadro"
    if organizacao not in VISOES + ("planner",):
        organizacao = "lista"
    dia = _parse_data(request.GET.get("data"))

    if organizacao == "planner" and request.method == "GET":
        return planner_views.planner(request, funcionario=funcionario, dia=dia)

    abrir_popup_tarefa = False
    form = AtividadeForm(ator=funcionario, initial={"planejado_para": dia})
    if request.method == "POST":
        acao = request.POST.get("acao") or "criar"
        if acao == "criar_rapida":
            return _criar_rapida(request, funcionario, dia)
        form = AtividadeForm(request.POST, ator=funcionario)
        if form.is_valid():
            criada = criar_atividade(
                funcionario,
                titulo=form.cleaned_data["titulo"],
                responsavel=form.cleaned_data.get("responsavel"),
                participantes=form.cleaned_data.get("participantes"),
                status=form.cleaned_data.get("status") or StatusAtividade.NAO_INICIADO,
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

    equipe = list(funcionarios_para_equipe(funcionario))
    tarefas = tarefas_para_visualizacoes(funcionario)
    if request.GET.get("formato") == "json":
        return JsonResponse({"ok": True, "tarefas": tarefas})
    # Inclui quem saiu da equipe mas ainda aparece em alguma tarefa.
    conhecidos = {f.pk for f in equipe}
    faltando = set()
    for t in tarefas:
        for tarefa in [t] + t.get("subtarefas", []):
            for pk in [tarefa["responsavel"]] + tarefa["participantes"]:
                if pk and pk not in conhecidos:
                    faltando.add(pk)
    pessoas = [serializar_pessoa(f) for f in equipe]
    if faltando:
        pessoas += [
            serializar_pessoa(f) for f in Funcionario.objects.filter(pk__in=faltando)
        ]

    hoje = timezone.localdate()
    pode_dirigir = pode_dirigir_atividades(funcionario)
    dados = {
        "hoje": hoje.isoformat(),
        "visao": organizacao,
        "eu": funcionario.pk,
        "pode_dirigir": pode_dirigir,
        "tarefas": tarefas,
        "pessoas": pessoas,
        "empresas": [{"id": c.pk, "nome": c.nome} for c in queryset_clientes_rsc()],
        "status": [{"valor": v, "label": l} for v, l in StatusAtividade.choices],
        "prioridades": [
            {"valor": v, "label": l} for v, l in PrioridadeAtividade.choices
        ],
        "urls": {
            "criar": reverse("atividades"),
            "reordenar": reverse("atividades_reordenar"),
        },
    }
    return render(
        request,
        "atividades/visualizacoes.html",
        {
            "form": form,
            "dados": dados,
            "organizacao": organizacao,
            "pode_dirigir": pode_dirigir,
            "eu": funcionario,
            "equipe_opcoes": equipe,
            "abrir_popup_tarefa": abrir_popup_tarefa,
            "dia": dia,
            "hoje": hoje,
        },
    )


@login_required
@require_POST
def atualizar_campos(request, pk: int):
    """Edição de um ou mais campos (menus de status, prioridade, data, painel)."""
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return _negar(request, "Sem perfil de funcionário.")
    item = get_object_or_404(
        AtividadeDiaria.objects.ativas().prefetch_related("participantes"), pk=pk
    )
    if not pode_gerenciar_atividade(funcionario, item):
        return _negar(request, "Sem permissão para editar esta tarefa.")

    post = request.POST
    alterados = []

    def _data(nome):
        valor = (post.get(nome) or "").strip()
        if not valor:
            return None
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Data inválida.") from exc

    try:
        if "titulo" in post:
            titulo = (post.get("titulo") or "").strip()
            if not titulo:
                return _negar(request, "O nome da tarefa não pode ficar vazio.", 400)
            item.titulo = titulo[:200]
            alterados.append("titulo")
        if "descricao" in post:
            item.descricao = (post.get("descricao") or "").strip()
            alterados.append("descricao")
        if "prioridade" in post:
            prio = post.get("prioridade") or PrioridadeAtividade.NENHUMA
            if prio not in PrioridadeAtividade.values:
                return _negar(request, "Prioridade inválida.", 400)
            item.prioridade = prio
            alterados.append("prioridade")
        if "data_vencimento" in post:
            item.data_vencimento = _data("data_vencimento")
            alterados.append("data_vencimento")
        if "planejado_para" in post:
            item.planejado_para = _data("planejado_para")
            alterados.append("planejado_para")
    except ValueError as exc:
        return _negar(request, str(exc), 400)
    if "empresa" in post:
        emp = (post.get("empresa") or "").strip()
        if emp:
            cliente = queryset_clientes_rsc().filter(pk=emp if emp.isdigit() else 0).first()
            if cliente is None:
                return _negar(request, "Empresa inválida.", 400)
            item.cliente_rsc = cliente
        else:
            item.cliente_rsc = None
        alterados.append("cliente_rsc")
    if "responsavel" in post:
        if not pode_dirigir_atividades(funcionario):
            return _negar(request, "Só gestores trocam o responsável principal.")
        resp_id = post.get("responsavel") or ""
        novo = (
            funcionarios_para_equipe(funcionario)
            .filter(pk=resp_id if resp_id.isdigit() else 0)
            .first()
        )
        if novo is None:
            return _negar(request, "Responsável inválido.", 400)
        item.responsavel = novo
        alterados.append("responsavel")

    rotulos = {
        "titulo": "o nome",
        "descricao": "a descrição",
        "prioridade": "a prioridade",
        "data_vencimento": "a data de entrega",
        "planejado_para": "o dia planejado",
        "cliente_rsc": "a empresa",
        "responsavel": "o responsável",
    }
    if alterados:
        item.save()
        registrar_evento(
            item,
            funcionario,
            TipoEventoAtividade.EDICAO,
            texto="Atualizou " + ", ".join(rotulos[c] for c in alterados) + ".",
        )
    if post.get("participantes_enviados") == "1":
        ids = [int(v) for v in post.getlist("participantes") if v.isdigit()]
        validos = funcionarios_para_equipe(funcionario).filter(pk__in=ids)
        definir_participantes(item, validos)
    return JsonResponse({"ok": True, "tarefa": _tarefa_json(item, funcionario)})


@login_required
@require_POST
def reordenar(request):
    """Ordem manual após arrastar; muda o status quando a tarefa troca de grupo."""
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return _negar(request, "Sem perfil de funcionário.")
    ids = [int(v) for v in request.POST.getlist("ids") if v.isdigit()]
    movida_id = request.POST.get("movida") or ""
    status = request.POST.get("status") or ""
    resposta = {"ok": True}
    if movida_id.isdigit() and status:
        if status not in StatusAtividade.values:
            return _negar(request, "Status inválido.", 400)
        movida = _atividade_ativa(int(movida_id))
        if not pode_alterar_status(funcionario, movida):
            return _negar(request, "Sem permissão para mudar o status desta tarefa.")
        alterar_status(movida, status, autor=funcionario)
        movida.refresh_from_db()
        resposta["tarefa"] = _tarefa_json(movida, funcionario)
    # A ordem só vale para tarefas que a pessoa pode alterar.
    permitidas = {
        a.pk
        for a in AtividadeDiaria.objects.ativas()
        .filter(pk__in=ids)
        .select_related("responsavel")
        .prefetch_related("participantes")
        if pode_alterar_status(funcionario, a)
    }
    reordenar_atividades([pk for pk in ids if pk in permitidas])
    return JsonResponse(resposta)


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
        if _quer_json(request):
            return JsonResponse(
                {
                    "ok": True,
                    "pk": item.pk,
                    "titulo": item.titulo,
                    "status": item.status,
                    "label": item.get_status_display(),
                    "aviso": aviso_hora or getattr(form, "aviso", ""),
                }
            )
    else:
        messages.error(request, "Não foi possível atualizar a tarefa.")
        if _quer_json(request):
            erro = next(iter(form.errors.values()), ["Não foi possível atualizar a tarefa."])[0]
            return JsonResponse({"ok": False, "erro": str(erro)}, status=400)
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
    if _quer_json(request):
        return JsonResponse({"ok": True, "pk": item.pk})
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
        if _quer_json(request):
            return _negar(request, "Não é possível criar subtarefa de outra subtarefa.", 400)
        messages.error(request, "Não é possível criar subtarefa de outra subtarefa.")
        return _redirect_lista(request)
    if not pode_gerenciar_atividade(funcionario, pai):
        return _negar(request, "Sem permissão para criar subtarefa.")

    titulo = (request.POST.get("titulo") or "").strip()
    if not titulo:
        if _quer_json(request):
            return _negar(request, "Informe o título da subtarefa.", 400)
        messages.error(request, "Informe o título da subtarefa.")
        return _redirect_lista(request)

    resp_id = request.POST.get("responsavel")
    responsavel = None
    if resp_id:
        responsavel = next(
            (f for f in funcionarios_para_equipe(funcionario) if str(f.pk) == str(resp_id)),
            None,
        )
    sub = criar_atividade(
        funcionario,
        titulo=titulo[:200],
        responsavel=responsavel or funcionario,
        atividade_pai=pai,
        status=StatusAtividade.NAO_INICIADO,
        prioridade=pai.prioridade,
        cliente_rsc=pai.cliente_rsc,
        planejado_para=pai.planejado_para,
    )
    if _quer_json(request):
        return JsonResponse({"ok": True, "pai": _tarefa_json(pai, funcionario), "pk": sub.pk})
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
    relogio = relogio_para(item, funcionario)
    if _quer_json(request):
        return JsonResponse(
            {
                "ok": True,
                "status": item.status,
                "label": item.get_status_display(),
                "cronometro_ativo": relogio["ativo"],
                "segundos": relogio["segundos"],
                "acumulado": relogio["acumulado"],
                "inicio": relogio["inicio"],
                "texto": relogio["texto"],
                "tarefa": _tarefa_json(item, funcionario),
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
    if item.status in STATUS_CONCLUIDOS and not item.cronometro_ativo_para(funcionario):
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
                **relogio_para(item, funcionario),
                "tarefa": _tarefa_json(item, funcionario),
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


@login_required
def detalhe(request, pk: int):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        return JsonResponse({"ok": False, "erro": "Sem perfil de funcionário."}, status=403)
    item = _atividade_ativa(pk)
    eventos = [
        {
            "id": ev.pk,
            "tipo": ev.tipo,
            "tipo_label": ev.get_tipo_display(),
            "texto": ev.texto,
            "autor": ev.autor.nome_completo if ev.autor_id else "Sistema",
            "quando": timezone.localtime(ev.criado_em).strftime("%d/%m %H:%M"),
        }
        for ev in item.eventos.select_related("autor")
    ]
    subtarefas = []
    for sub in item.subtarefas.filter(deletado_em__isnull=True).select_related("responsavel"):
        subtarefas.append(
            {
                "id": sub.pk,
                "titulo": sub.titulo,
                "status": sub.status,
                "responsavel": sub.responsavel.nome_completo if sub.responsavel_id else "",
                "responsavel_id": sub.responsavel_id,
                "pode_marcar": pode_alterar_status(funcionario, sub),
            }
        )
    por_pessoa: dict[int, dict] = {}
    for sessao in item.sessoes_tempo.select_related("funcionario"):
        linha = por_pessoa.setdefault(
            sessao.funcionario_id,
            {
                "id": sessao.funcionario_id,
                "nome": sessao.funcionario.nome_completo,
                "segundos": 0,
                "rodando": False,
            },
        )
        linha["segundos"] += sessao.segundos_atuais()
        if sessao.fim is None:
            linha["rodando"] = True
    return JsonResponse(
        {
            "ok": True,
            "pode_editar": pode_gerenciar_atividade(funcionario, item),
            "eventos": eventos,
            "subtarefas": subtarefas,
            "tempo_por_pessoa": sorted(
                por_pessoa.values(), key=lambda p: -p["segundos"]
            ),
        }
    )
