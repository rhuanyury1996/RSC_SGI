from django.conf import settings
from django.db import models

from funcionarios.models import Funcionario

MAX_HORAS_RECUPERACAO_POR_DIA = 2


class TipoEvento(models.TextChoices):
    FERIAS = "ferias", "Férias"
    DAY_OFF = "day_off", "Day off"
    REUNIAO = "reuniao", "Reunião"
    DEMANDA = "demanda", "Demanda"
    RECUPERACAO = "recuperacao", "Recuperação de horas"


class StatusEvento(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    CONFIRMADO = "confirmado", "Confirmado"
    CONCLUIDO = "concluido", "Concluído"
    CANCELADO = "cancelado", "Cancelado"


class StatusDemanda(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    CONCLUIDA = "concluida", "Concluída"
    CANCELADA = "cancelada", "Cancelada"


class EventoCalendario(models.Model):
    tipo = models.CharField("Tipo", max_length=20, choices=TipoEvento.choices)
    titulo = models.CharField("Título", max_length=200)
    motivo = models.TextField("Motivo / descrição", blank=True)
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="eventos_calendario",
        verbose_name="Responsável",
    )
    inicio = models.DateTimeField("Início")
    fim = models.DateTimeField("Fim")
    dia_inteiro = models.BooleanField("Dia inteiro", default=True)
    status = models.CharField(
        max_length=20,
        choices=StatusEvento.choices,
        default=StatusEvento.CONFIRMADO,
    )
    horas_recuperar = models.DecimalField(
        "Horas a recuperar",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    recuperacao_inicio = models.DateField(
        "Início do período de recuperação",
        null=True,
        blank=True,
    )
    recuperacao_fim = models.DateField(
        "Fim do período de recuperação",
        null=True,
        blank=True,
    )
    google_event_id = models.CharField(
        "ID no Google Calendar",
        max_length=255,
        blank=True,
        default="",
    )
    espelhado_google = models.BooleanField("Espelhado no Google", default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Evento do calendário"
        verbose_name_plural = "Eventos do calendário"
        ordering = ["inicio"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()}: {self.titulo}"

    @property
    def cor(self) -> str:
        return {
            TipoEvento.FERIAS: "#14b8a6",
            TipoEvento.DAY_OFF: "#ff6b4a",
            TipoEvento.REUNIAO: "#7c6cf0",
            TipoEvento.DEMANDA: "#f43f8b",
            TipoEvento.RECUPERACAO: "#f59e0b",
        }.get(self.tipo, "#6b7280")


class Demanda(models.Model):
    """Demandas geradas (ex.: recuperação de horas de day-off) ou manuais."""

    titulo = models.CharField("Título", max_length=200)
    descricao = models.TextField("Descrição", blank=True)
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="demandas",
        verbose_name="Responsável",
    )
    evento_origem = models.ForeignKey(
        EventoCalendario,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="demandas_geradas",
        verbose_name="Evento de origem",
    )
    evento_agenda = models.ForeignKey(
        EventoCalendario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandas_agendadas",
        verbose_name="Evento na agenda",
    )
    data_prevista = models.DateField("Data prevista")
    horas = models.DecimalField(
        "Horas",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=StatusDemanda.choices,
        default=StatusDemanda.PENDENTE,
    )
    origem_day_off = models.BooleanField("Veio de day-off", default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Demanda"
        verbose_name_plural = "Demandas"
        ordering = ["data_prevista", "-criado_em"]

    def __str__(self) -> str:
        return self.titulo


class GoogleCalendarConta(models.Model):
    """Credenciais OAuth do Google Calendar por usuário do sistema."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="google_calendar",
        verbose_name="Usuário",
    )
    email = models.EmailField("E-mail Google", blank=True)
    token = models.TextField("Access token")
    refresh_token = models.TextField("Refresh token", blank=True)
    token_uri = models.CharField(max_length=255, default="https://oauth2.googleapis.com/token")
    client_id = models.CharField(max_length=255, blank=True)
    client_secret = models.CharField(max_length=255, blank=True)
    scopes = models.TextField(blank=True)
    expiry = models.DateTimeField(null=True, blank=True)
    conectado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conta Google Calendar"
        verbose_name_plural = "Contas Google Calendar"

    def __str__(self) -> str:
        return self.email or f"Google de {self.usuario}"

    @property
    def conectado(self) -> bool:
        return bool(self.refresh_token or self.token)
