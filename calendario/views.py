from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from funcionarios.utils import obter_funcionario

from .forms import EventoCalendarioForm
from .google_sync import (
    build_flow,
    espelhar_evento_google,
    espelhar_pendentes,
    google_configurado,
    save_credentials,
)
from .models import EventoCalendario, GoogleCalendarConta, StatusEvento, TipoEvento
from .services import (
    atividade_para_item,
    eventos_do_dia,
    garantir_demanda_recuperacao,
    montar_mes,
)


def _exige_funcionario(request):
    funcionario = obter_funcionario(request)
    if funcionario is None:
        messages.error(request, "É necessário ter um perfil de funcionário vinculado.")
        return None
    return funcionario


def _google_status(user):
    configurado = google_configurado()
    conta = GoogleCalendarConta.objects.filter(usuario=user).first()
    return {
        "google_configurado": configurado,
        "google_conectado": bool(conta and conta.conectado),
        "google_email": conta.email if conta else "",
    }


def _normalizar_dia_inteiro(evento: EventoCalendario) -> None:
    if not evento.dia_inteiro:
        return
    ini = timezone.localtime(evento.inicio).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    fim = timezone.localtime(evento.fim).replace(
        hour=23, minute=59, second=0, microsecond=0
    )
    evento.inicio = ini
    evento.fim = fim


def _espelhar_lista(request, eventos: list[EventoCalendario], google: dict) -> None:
    if not google.get("google_conectado"):
        return
    google_ok = 0
    google_fail = 0
    for ev in eventos:
        if not ev:
            continue
        if espelhar_evento_google(request.user, ev):
            google_ok += 1
        else:
            google_fail += 1
    if google_ok:
        messages.info(
            request,
            f"Espelhado no Google Calendar ({google_ok} evento(s)).",
        )
    if google_fail:
        messages.warning(
            request,
            "Falha ao espelhar no Google. Tente reconectar a conta.",
        )


def _persistir_evento(
    request,
    form: EventoCalendarioForm,
    funcionario,
    google: dict,
    *,
    novo: bool,
) -> EventoCalendario:
    evento = form.save(commit=False)
    evento.funcionario = funcionario
    if not evento.titulo:
        evento.titulo = evento.get_tipo_display()
    _normalizar_dia_inteiro(evento)
    evento.save()

    eventos_para_google = [evento]
    if evento.tipo == TipoEvento.DAY_OFF:
        demandas = garantir_demanda_recuperacao(evento)
        messages.success(
            request,
            (
                f"{'Day-off atualizado' if not novo else 'Day-off registrado'}. "
                f"{len(demandas)} demanda(s) de recuperação "
                f"{'atualizada(s)' if not novo else 'criada(s)'} (máx. 2h/dia)."
            ),
        )
        eventos_para_google = [evento] + [
            d.evento_agenda for d in demandas if d.evento_agenda_id
        ]
    else:
        messages.success(
            request,
            "Evento atualizado." if not novo else "Evento adicionado ao calendário.",
        )

    _espelhar_lista(request, eventos_para_google, google)
    return evento


@login_required
def calendario(request):
    funcionario = _exige_funcionario(request)
    if funcionario is None:
        return redirect("home")

    hoje = timezone.localdate()
    try:
        ano = int(request.POST.get("ano") or request.GET.get("ano") or hoje.year)
    except (TypeError, ValueError):
        ano = hoje.year
    try:
        mes = int(request.POST.get("mes") or request.GET.get("mes") or hoje.month)
    except (TypeError, ValueError):
        mes = hoje.month
    if mes < 1 or mes > 12:
        mes = hoje.month

    tipos_raw = request.GET.getlist("tipo")
    tipos_validos = {c.value for c in TipoEvento}
    if tipos_raw:
        tipos_filtro = [t for t in tipos_raw if t in tipos_validos]
        mostrar_atividades = "atividade" in tipos_raw
    else:
        tipos_filtro = list(tipos_validos)
        mostrar_atividades = True
    filtros_ativos = set(tipos_filtro)
    if mostrar_atividades:
        filtros_ativos.add("atividade")

    visao = (request.GET.get("visao") or request.POST.get("visao") or "minhas").strip()
    if visao not in ("minhas", "equipe"):
        visao = "minhas"
    ver_equipe = visao == "equipe"

    google = _google_status(request.user)
    evento_edit = None
    abrir_dialog = False

    def _qs_visao(extra: str = ""):
        return f"{request.path}?ano={ano}&mes={mes}&visao={visao}{extra}"

    if request.method == "POST":
        acao = (request.POST.get("acao") or "salvar").strip()
        evento_id = (request.POST.get("evento_id") or "").strip()
        if evento_id:
            evento_edit = get_object_or_404(
                EventoCalendario,
                pk=evento_id,
                funcionario=funcionario,
            )

        if acao == "excluir" and evento_edit is not None:
            evento_edit.status = StatusEvento.CANCELADO
            evento_edit.save(update_fields=["status", "atualizado_em"])
            messages.success(request, "Evento removido do calendário.")
            return redirect(_qs_visao())

        if acao == "duplicar" and evento_edit is not None:
            copia = EventoCalendario.objects.get(pk=evento_edit.pk)
            copia.pk = None
            copia.id = None
            copia.titulo = f"{evento_edit.titulo} (cópia)"
            copia.status = StatusEvento.CONFIRMADO
            copia.google_event_id = ""
            copia.espelhado_google = False
            # Empurra 7 dias para não sobrepor o original no mesmo dia
            copia.inicio = evento_edit.inicio + timedelta(days=7)
            copia.fim = evento_edit.fim + timedelta(days=7)
            if evento_edit.recuperacao_inicio:
                copia.recuperacao_inicio = evento_edit.recuperacao_inicio + timedelta(
                    days=7
                )
            if evento_edit.recuperacao_fim:
                copia.recuperacao_fim = evento_edit.recuperacao_fim + timedelta(days=7)
            copia.save()
            if copia.tipo == TipoEvento.DAY_OFF:
                demandas = garantir_demanda_recuperacao(copia)
                _espelhar_lista(
                    request,
                    [copia]
                    + [d.evento_agenda for d in demandas if d.evento_agenda_id],
                    google,
                )
            else:
                _espelhar_lista(request, [copia], google)
            messages.success(request, "Evento duplicado (+7 dias).")
            return redirect(_qs_visao(f"&evento={copia.pk}"))

        if evento_edit is not None:
            form = EventoCalendarioForm(
                request.POST, instance=evento_edit, funcionario=funcionario
            )
        else:
            form = EventoCalendarioForm(request.POST, funcionario=funcionario)

        if form.is_valid():
            evento = _persistir_evento(
                request,
                form,
                funcionario,
                google,
                novo=evento_edit is None,
            )
            return redirect(_qs_visao(f"&evento={evento.pk}"))
        abrir_dialog = True
    else:
        evento_id = (request.GET.get("evento") or "").strip()
        if evento_id:
            evento_edit = get_object_or_404(
                EventoCalendario,
                pk=evento_id,
                funcionario=funcionario,
            )
            form = EventoCalendarioForm(
                instance=evento_edit, funcionario=funcionario
            )
            abrir_dialog = True
        else:
            form = EventoCalendarioForm(funcionario=funcionario)

    primeiro = date(ano, mes, 1)
    if mes == 12:
        ultimo = date(ano + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo = date(ano, mes + 1, 1) - timedelta(days=1)
    janela_ini = primeiro - timedelta(days=7)
    janela_fim = ultimo + timedelta(days=7)

    itens: list = []
    if tipos_filtro:
        qs = (
            EventoCalendario.objects.filter(
                inicio__date__lte=janela_fim,
                fim__date__gte=janela_ini,
                tipo__in=tipos_filtro,
            )
            .exclude(status="cancelado")
            .select_related("funcionario")
        )
        if not ver_equipe:
            qs = qs.filter(funcionario=funcionario)
        eventos = list(qs)
        if ver_equipe:
            for ev in eventos:
                # Anexa rótulo de pessoa para a grade sem alterar o modelo
                ev._pessoa_label = ev.funcionario.nome if ev.funcionario_id else ""
                ev._editavel = ev.funcionario_id == funcionario.id
                if ev._pessoa_label and ev.funcionario_id != funcionario.id:
                    ev.titulo_exibicao = f"{ev.titulo} · {ev._pessoa_label}"
                else:
                    ev.titulo_exibicao = ev.titulo
        else:
            for ev in eventos:
                ev._pessoa_label = ""
                ev._editavel = True
                ev.titulo_exibicao = ev.titulo
        itens.extend(eventos)

    if mostrar_atividades:
        from atividades.models import AtividadeDiaria

        atividades_qs = AtividadeDiaria.objects.filter(
            planejado_para__gte=janela_ini,
            planejado_para__lte=janela_fim,
        ).select_related("responsavel")
        if not ver_equipe:
            atividades_qs = atividades_qs.filter(responsavel=funcionario)
        atividades = atividades_qs.order_by(
            "planejado_para", "hora_inicio", "ordem", "pk"
        )
        for at in atividades:
            item = atividade_para_item(at, mostrar_pessoa=ver_equipe)
            if item:
                itens.append(item)

    semanas = montar_mes(ano, mes, itens)
    hoje_eventos = eventos_do_dia(itens, hoje)

    mes_anterior = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    mes_seguinte = (ano, mes + 1) if mes < 12 else (ano + 1, 1)
    nomes_mes = [
        "",
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]
    mini = montar_mes(ano, mes, itens)

    return render(
        request,
        "calendario/calendario.html",
        {
            "form": form,
            "evento_edit": evento_edit,
            "abrir_dialog": abrir_dialog,
            "semanas": semanas,
            "mini": mini,
            "ano": ano,
            "mes": mes,
            "mes_nome": nomes_mes[mes],
            "mes_anterior": mes_anterior,
            "mes_seguinte": mes_seguinte,
            "hoje_eventos": hoje_eventos,
            "tipos": TipoEvento,
            "tipos_filtro": filtros_ativos,
            "mostrar_atividades": mostrar_atividades,
            "hoje": hoje,
            "visao": visao,
            "ver_equipe": ver_equipe,
            "eu": funcionario,
            **google,
        },
    )


@login_required
def google_conectar(request):
    if not google_configurado():
        messages.error(
            request,
            "Google Calendar não configurado. Defina GOOGLE_CLIENT_ID e "
            "GOOGLE_CLIENT_SECRET no .env.",
        )
        return redirect("calendario")

    flow = build_flow(request)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["google_oauth_state"] = state
    return redirect(auth_url)


@login_required
def google_callback(request):
    if not google_configurado():
        messages.error(request, "Google Calendar não configurado.")
        return redirect("calendario")

    state = request.session.get("google_oauth_state")
    if not state or state != request.GET.get("state"):
        messages.error(request, "Falha na autenticação Google (state inválido).")
        return redirect("calendario")

    if request.GET.get("error"):
        messages.error(request, "Autorização Google cancelada.")
        return redirect("calendario")

    try:
        flow = build_flow(request, state=state)
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials
        save_credentials(request.user, credentials)
        messages.success(request, "Google Calendar conectado com sucesso.")

        funcionario = obter_funcionario(request)
        if funcionario:
            ok, falhas = espelhar_pendentes(request.user, funcionario)
            if ok:
                messages.info(
                    request,
                    f"{ok} evento(s) existente(s) espelhado(s) para o Google Calendar.",
                )
            if falhas:
                messages.warning(
                    request,
                    f"{falhas} evento(s) não puderam ser espelhados agora.",
                )
    except Exception:
        messages.error(
            request,
            "Não foi possível concluir a conexão com o Google Calendar.",
        )
    return redirect("calendario")


@login_required
def google_desconectar(request):
    GoogleCalendarConta.objects.filter(usuario=request.user).delete()
    messages.info(request, "Google Calendar desconectado deste usuário.")
    return redirect("calendario")


@login_required
def demandas(request):
    """Página removida — horas a recuperar ficam em Apontamentos."""
    return redirect("apontamentos")


@login_required
def demanda_status(request, pk: int):
    """Compatibilidade: redireciona atualizações para Apontamentos."""
    return redirect("apontamentos")
