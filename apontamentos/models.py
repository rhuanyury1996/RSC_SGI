from django.conf import settings
from django.db import models

from funcionarios.models import Funcionario


class TipoMarcacao(models.TextChoices):
    ENTRADA = "entrada", "Entrada"
    SAIDA = "saida", "Saída"
    CAFE_INICIO = "cafe_inicio", "Café — início"
    CAFE_FIM = "cafe_fim", "Café — fim"
    ALMOCO_INICIO = "almoco_inicio", "Almoço — início"
    ALMOCO_FIM = "almoco_fim", "Almoço — fim"
    OUTRO = "outro", "Outro"


class StatusSolicitacao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    APROVADA = "aprovada", "Aprovada"
    RECUSADA = "recusada", "Recusada"
    CANCELADA = "cancelada", "Cancelada"


class MarcacaoPonto(models.Model):
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="marcacoes",
        verbose_name="Funcionário",
    )
    tipo = models.CharField("Tipo", max_length=20, choices=TipoMarcacao.choices)
    data_hora = models.DateTimeField("Data/hora")
    observacao = models.CharField("Observação", max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Marcação de ponto"
        verbose_name_plural = "Marcações de ponto"
        ordering = ["-data_hora"]

    def __str__(self) -> str:
        return f"{self.funcionario} — {self.get_tipo_display()} @ {self.data_hora}"


class TipoSolicitacaoMarcacao(models.TextChoices):
    EDICAO = "edicao", "Edição"
    EXCLUSAO = "exclusao", "Exclusão"


class SolicitacaoEdicaoMarcacao(models.Model):
    """Pedido de correção ou exclusão — só aplica após aprovação do Rhuan."""

    marcacao = models.ForeignKey(
        MarcacaoPonto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitacoes_edicao",
        verbose_name="Marcação",
    )
    tipo_solicitacao = models.CharField(
        "Tipo de solicitação",
        max_length=20,
        choices=TipoSolicitacaoMarcacao.choices,
        default=TipoSolicitacaoMarcacao.EDICAO,
    )
    solicitado_por = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="solicitacoes_edicao_marcacao",
        verbose_name="Solicitado por",
    )
    tipo_original = models.CharField(max_length=20, choices=TipoMarcacao.choices)
    data_hora_original = models.DateTimeField()
    observacao_original = models.CharField(max_length=255, blank=True)
    tipo_proposto = models.CharField(max_length=20, choices=TipoMarcacao.choices)
    data_hora_proposta = models.DateTimeField()
    observacao_proposta = models.CharField(max_length=255, blank=True)
    motivo = models.TextField("Motivo")
    status = models.CharField(
        max_length=20,
        choices=StatusSolicitacao.choices,
        default=StatusSolicitacao.PENDENTE,
    )
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edicoes_marcacao_revisadas",
        verbose_name="Revisado por",
    )
    revisado_em = models.DateTimeField(null=True, blank=True)
    nota_revisao = models.CharField("Nota da revisão", max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Solicitação de alteração de marcação"
        verbose_name_plural = "Solicitações de alteração de marcação"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        alvo = self.marcacao or f"{self.get_tipo_original_display()} @ {self.data_hora_original}"
        return f"{self.get_tipo_solicitacao_display()} #{self.pk} — {alvo} ({self.get_status_display()})"

    @property
    def is_exclusao(self) -> bool:
        return self.tipo_solicitacao == TipoSolicitacaoMarcacao.EXCLUSAO

    def aplicar_se_aprovada(self) -> None:
        if self.status != StatusSolicitacao.APROVADA:
            return
        if self.tipo_solicitacao == TipoSolicitacaoMarcacao.EXCLUSAO:
            if self.marcacao_id:
                self.marcacao.delete()
            return
        if not self.marcacao_id:
            return
        marcacao = self.marcacao
        marcacao.tipo = self.tipo_proposto
        marcacao.data_hora = self.data_hora_proposta
        marcacao.observacao = self.observacao_proposta
        marcacao.save(update_fields=["tipo", "data_hora", "observacao"])


class SolicitacaoFerias(models.Model):
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="ferias",
        verbose_name="Funcionário",
    )
    data_inicio = models.DateField("Início")
    data_fim = models.DateField("Fim")
    status = models.CharField(
        max_length=20,
        choices=StatusSolicitacao.choices,
        default=StatusSolicitacao.PENDENTE,
    )
    observacao = models.TextField("Observação", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Solicitação de férias"
        verbose_name_plural = "Solicitações de férias"
        ordering = ["-data_inicio"]

    def __str__(self) -> str:
        return f"Férias {self.funcionario} ({self.data_inicio} → {self.data_fim})"


class SolicitacaoDayOff(models.Model):
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name="day_offs",
        verbose_name="Funcionário",
    )
    data = models.DateField("Data")
    motivo = models.TextField("Motivo", blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusSolicitacao.choices,
        default=StatusSolicitacao.PENDENTE,
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Solicitação de day off"
        verbose_name_plural = "Solicitações de day off"
        ordering = ["-data"]

    def __str__(self) -> str:
        return f"Day off {self.funcionario} em {self.data}"
