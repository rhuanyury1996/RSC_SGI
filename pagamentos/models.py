from django.db import models

from funcionarios.models import Funcionario


class TipoPagamento(models.TextChoices):
    A_PAGAR = "a_pagar", "A pagar"
    A_RECEBER = "a_receber", "A receber"


class StatusPagamento(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    PAGO = "pago", "Pago"
    CANCELADO = "cancelado", "Cancelado"


class Pagamento(models.Model):
    descricao = models.CharField("Descrição", max_length=255)
    tipo = models.CharField(max_length=20, choices=TipoPagamento.choices)
    valor = models.DecimalField("Valor", max_digits=12, decimal_places=2)
    data_vencimento = models.DateField("Vencimento")
    data_pagamento = models.DateField("Data do pagamento", null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=StatusPagamento.choices,
        default=StatusPagamento.PENDENTE,
    )
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pagamentos",
        verbose_name="Funcionário relacionado",
    )
    observacao = models.TextField("Observação", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        ordering = ["-data_vencimento"]

    def __str__(self) -> str:
        return f"{self.descricao} ({self.get_status_display()})"
