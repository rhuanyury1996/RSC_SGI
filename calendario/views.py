from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
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
from .models import EventoCalendario, GoogleCalendarConta, TipoEvento
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


@login_required
def calendario(request):
    funcionario = _exige_funcionario(request)
    if funcionario is None:
        return redirect("home")

    hoje = timezone.localdate()
    ano = int(request.GET.get("ano", hoje.year))
    mes = int(request.GET.get("mes", hoje.month))
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

    google = _google_status(request.user)

    if request.method == "POST":
        form = EventoCalendarioForm(request.POST, funcionario=funcionario)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.funcionario = funcionario
            if not evento.titulo:
                evento.titulo = evento.get_tipo_display()
            if evento.dia_inteiro:
                ini = timezone.localtime(evento.inicio).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                fim = timezone.localtime(evento.fim).replace(
                    hour=23, minute=59, second=0, microsecond=0
                )
                evento.inicio = ini
                evento.fim = fim
            evento.save()

            if evento.tipo == TipoEvento.DAY_OFF:
                demandas = garantir_demanda_recuperacao(evento)
                messages.success(
                    request,
                    (
                        f"Day-off registrado. {len(demandas)} demanda(s) de recuperação "
                        f"criada(s) (máx. 2h/dia)."
                    ),
                )
                eventos_para_google = [evento] + [
                    d.evento_agenda for d in demandas if d.evento_agenda_id
                ]
            else:
                messages.success(request, "Evento adicionado ao calendário.")
                eventos_para_google = [evento]

            # Se a conta Google estiver conectada, espelha automaticamente
            if google["google_conectado"]:
                google_ok = 0
                google_fail = 0
                for ev in eventos_para_google:
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

            return redirect(f"{request.path}?ano={ano}&mes={mes}")
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
                funcionario=funcionario,
                inicio__date__lte=janela_fim,
                fim__date__gte=janela_ini,
                tipo__in=tipos_filtro,
            )
            .exclude(status="cancelado")
            .select_related("funcionario")
        )
        itens.extend(qs)

    if mostrar_atividades:
        from atividades.models import AtividadeDiaria

        atividades = AtividadeDiaria.objects.filter(
            responsavel=funcionario,
            planejado_para__gte=janela_ini,
            planejado_para__lte=janela_fim,
        ).order_by("planejado_para", "hora_inicio", "ordem", "pk")
        for at in atividades:
            item = atividade_para_item(at)
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
