from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import AlterarSenhaForm, LoginForm, PerfilForm
from .models import Funcionario
from .utils import obter_funcionario


def _saudacao(agora=None) -> str:
    agora = agora or timezone.localtime()
    hora = agora.hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"


def _partes_countdown(alvo, agora=None) -> dict:
    agora = agora or timezone.localtime()
    if timezone.is_naive(alvo):
        alvo = timezone.make_aware(alvo, timezone.get_current_timezone())
    delta = alvo - agora
    total = max(0, int(delta.total_seconds()))
    dias, resto = divmod(total, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, segundos = divmod(resto, 60)
    return {
        "total_segundos": total,
        "dias": dias,
        "horas": horas,
        "minutos": minutos,
        "segundos": segundos,
        "chegou": total == 0,
    }


def _proximo_evento_calendario(funcionario: Funcionario, tipo: str, agora=None):
    from calendario.models import EventoCalendario, StatusEvento

    agora = agora or timezone.localtime()
    evento = (
        EventoCalendario.objects.filter(
            funcionario=funcionario,
            tipo=tipo,
            inicio__gte=agora,
        )
        .exclude(status=StatusEvento.CANCELADO)
        .order_by("inicio")
        .first()
    )
    if evento is None:
        return None
    partes = _partes_countdown(evento.inicio, agora)
    return {
        "evento": evento,
        "titulo": evento.titulo,
        "inicio": evento.inicio,
        "inicio_iso": timezone.localtime(evento.inicio).isoformat(),
        "data_label": timezone.localtime(evento.inicio).strftime("%d/%m/%Y"),
        **partes,
    }


def _montar_contexto_dashboard(funcionario: Funcionario) -> dict:
    from apontamentos.models import MarcacaoPonto
    from apontamentos.services import (
        formatar_duracao,
        inicio_semana,
        jornada_diaria_segundos,
        jornada_em_andamento,
        limitar_ao_marco_zero,
        montar_dashboard,
        segundos_trabalhados,
    )
    from atividades.models import AtividadeDiaria, PrioridadeAtividade, StatusAtividade
    from atividades.services import (
        formatar_tempo,
        metricas_planner,
        resumo_agua_habitos_semana,
    )
    from informativos.models import Informativo
    from .models import Cargo

    hoje = timezone.localdate()
    agora = timezone.localtime()
    nome = funcionario.nome or funcionario.nome_completo.split()[0]

    atividades = list(
        AtividadeDiaria.objects.filter(
            responsavel=funcionario,
            planejado_para=hoje,
        )
        .select_related("responsavel")
        .order_by("ordem", "hora_inicio", "pk")
    )
    produtividade = metricas_planner(funcionario, hoje, atividades)
    bemestar = resumo_agua_habitos_semana(funcionario, hoje)
    for item in atividades:
        item.tempo_fmt = formatar_tempo(item.tempo_atual_segundos())

    status_cards = [
        {
            "chave": "pendentes",
            "rotulo": "Pendentes",
            "valor": produtividade["pendentes"],
            "tom": "amber",
            "hint": "Ainda não iniciadas",
        },
        {
            "chave": "executando",
            "rotulo": "Em execução",
            "valor": produtividade["em_andamento"],
            "tom": "blue",
            "hint": "Com foco agora",
        },
        {
            "chave": "feitos",
            "rotulo": "Concluídas",
            "valor": produtividade["feitos"],
            "tom": "green",
            "hint": "Feitas hoje",
        },
        {
            "chave": "foco",
            "rotulo": "Tempo em tarefas",
            "valor": produtividade["focus_time"],
            "tom": "cyan",
            "hint": "Cronômetro do dia",
        },
        {
            "chave": "score",
            "rotulo": "Focus score",
            "valor": f'{produtividade["focus_score"]}/10',
            "tom": "violet",
            "hint": "Conclusão + foco",
        },
    ]

    urgentes = sum(
        1
        for a in atividades
        if a.prioridade == PrioridadeAtividade.URGENTE
        and a.status != StatusAtividade.REALIZADO
    )
    em_timer = next((a for a in atividades if a.cronometro_ativo), None)

    inicio_periodo = limitar_ao_marco_zero(inicio_semana(hoje))
    marcacoes_periodo = list(
        MarcacaoPonto.objects.filter(
            funcionario=funcionario,
            data_hora__date__gte=inicio_periodo,
            data_hora__date__lte=hoje,
        ).order_by("data_hora")
    )
    horas_periodo = montar_dashboard(
        marcacoes_periodo, inicio_periodo, hoje, funcionario
    )
    marcacoes_hoje = [
        m
        for m in marcacoes_periodo
        if timezone.localtime(m.data_hora).date() == hoje
    ]
    segundos_hoje = segundos_trabalhados(marcacoes_hoje)
    jornada_seg = jornada_diaria_segundos(funcionario)
    pct_jornada = (
        min(100, int(round((segundos_hoje / jornada_seg) * 100))) if jornada_seg else 0
    )

    from calendario.models import Demanda, StatusDemanda, TipoEvento

    countdown_dayoff = _proximo_evento_calendario(
        funcionario, TipoEvento.DAY_OFF, agora
    )
    countdown_ferias = _proximo_evento_calendario(
        funcionario, TipoEvento.FERIAS, agora
    )

    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)
    demandas_semana = list(
        Demanda.objects.filter(
            funcionario=funcionario,
            data_prevista__gte=inicio_semana,
            data_prevista__lte=fim_semana,
        )
        .exclude(status=StatusDemanda.CANCELADA)
        .order_by("data_prevista", "status", "-criado_em")[:10]
    )

    cargos_chefia = [Cargo.GERENTE, Cargo.SOCIO, Cargo.SUPERVISOR]
    autores_chefia = list(
        Funcionario.objects.filter(ativo=True, cargo__in=cargos_chefia)
        .exclude(usuario_id=None)
        .values_list("usuario_id", flat=True)
    )
    if funcionario.responde_a_id and funcionario.responde_a.usuario_id:
        autores_chefia.append(funcionario.responde_a.usuario_id)
    autores_chefia = list({uid for uid in autores_chefia if uid})

    avisos_qs = Informativo.objects.filter(ativo=True).select_related("autor")
    if autores_chefia:
        avisos_qs = avisos_qs.filter(autor_id__in=autores_chefia)
    avisos_chefe = list(avisos_qs.order_by("-publicado_em")[:8])

    return {
        "saudacao": _saudacao(agora),
        "nome_curto": nome,
        "hoje": hoje,
        "produtividade": produtividade,
        "status_cards": status_cards,
        "atividades_hoje": atividades[:12],
        "atividades_total_hoje": len(atividades),
        "urgentes_hoje": urgentes,
        "em_timer": em_timer,
        "horas_hoje": formatar_duracao(segundos_hoje),
        "horas_hoje_seg": segundos_hoje,
        "pct_jornada": pct_jornada,
        "jornada_alvo": formatar_duracao(jornada_seg),
        "em_andamento": jornada_em_andamento(marcacoes_hoje),
        "marcacoes_hoje": marcacoes_hoje[-6:],
        "horas_periodo": horas_periodo,
        "inicio_semana": inicio_semana,
        "fim_semana": fim_semana,
        "demandas_semana": demandas_semana,
        "avisos_chefe": avisos_chefe,
        "countdown_dayoff": countdown_dayoff,
        "countdown_ferias": countdown_ferias,
        "bemestar": bemestar,
        "status_labels": dict(StatusAtividade.choices),
        "prioridade_labels": dict(PrioridadeAtividade.choices),
    }


class AcessoLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        # Reabre o convite de Gmail em cada login até vincular
        self.request.session.pop("gmail_popup_dismissed", None)
        return response


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    messages.info(request, "Você saiu da sua conta.")
    return redirect("login")


@login_required
def home(request: HttpRequest) -> HttpResponse:
    funcionario = obter_funcionario(request)
    if funcionario is None and not request.user.is_superuser:
        messages.warning(
            request,
            "Seu usuário ainda não está vinculado a um cadastro de funcionário. "
            "Peça ao administrador para vincular.",
        )

    contexto = {"funcionario": funcionario}
    if funcionario is not None:
        contexto.update(_montar_contexto_dashboard(funcionario))
    else:
        contexto.update(
            {
                "saudacao": _saudacao(),
                "nome_curto": request.user.first_name or request.user.username,
            }
        )

    return render(request, "funcionarios/home.html", contexto)


@login_required
def meu_perfil(request: HttpRequest) -> HttpResponse:
    funcionario = obter_funcionario(request)
    if funcionario is None:
        if request.user.is_superuser:
            messages.info(
                request,
                "Conta de administrador sem perfil de funcionário vinculado.",
            )
            return redirect("home")
        messages.error(request, "Perfil de funcionário não encontrado.")
        return redirect("home")

    return render(
        request,
        "funcionarios/perfil.html",
        {"funcionario": funcionario},
    )


@login_required
def editar_perfil(request: HttpRequest) -> HttpResponse:
    funcionario = obter_funcionario(request)
    if funcionario is None:
        messages.error(request, "Perfil de funcionário não encontrado.")
        return redirect("home")

    if request.method == "POST":
        form = PerfilForm(request.POST, request.FILES, instance=funcionario)
        if form.is_valid():
            form.save()
            user = request.user
            user.first_name = form.cleaned_data["nome"]
            user.last_name = form.cleaned_data["sobrenome"]
            user.save(update_fields=["first_name", "last_name"])
            messages.success(request, "Perfil atualizado com sucesso.")
            return redirect("meu_perfil")
    else:
        form = PerfilForm(instance=funcionario)

    return render(
        request,
        "funcionarios/editar_perfil.html",
        {"form": form, "funcionario": funcionario},
    )


@login_required
def alterar_senha(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AlterarSenhaForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Senha alterada com sucesso.")
            return redirect("meu_perfil")
    else:
        form = AlterarSenhaForm(request.user)

    return render(request, "funcionarios/alterar_senha.html", {"form": form})


@login_required
def organograma(request: HttpRequest) -> HttpResponse:
    funcionarios = list(
        Funcionario.objects.filter(ativo=True)
        .select_related("responde_a")
        .order_by("nome", "sobrenome")
    )
    filhos: dict[int | None, list[Funcionario]] = defaultdict(list)
    for f in funcionarios:
        chave = f.responde_a_id
        filhos[chave].append(f)

    def montar(no: Funcionario | None):
        chave = no.pk if no else None
        return [
            {
                "funcionario": filho,
                "filhos": montar(filho),
            }
            for filho in filhos.get(chave, [])
        ]

    # Raízes: sem superior ou superior inativo/ausente
    ids = {f.pk for f in funcionarios}
    raizes = [
        {"funcionario": f, "filhos": montar(f)}
        for f in funcionarios
        if f.responde_a_id is None or f.responde_a_id not in ids
    ]

    return render(
        request,
        "funcionarios/organograma.html",
        {"raizes": raizes, "total": len(funcionarios)},
    )
