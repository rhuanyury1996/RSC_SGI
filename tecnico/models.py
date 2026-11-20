"""Setor Técnico: estudos de classificação de áreas (ABNT NBR IEC 60079-10-1).

O estado completo da calculadora (produtos, misturas, fontes, ventilação,
dispersão, extensões e dados do estudo) fica em `estado` (JSON), no mesmo
formato que a calculadora usa no navegador. Os campos de cabeçalho
(nome, cliente, revisão) são espelhados para listar e filtrar sem abrir o JSON.
"""
from django.db import models


class StatusEstudo(models.TextChoices):
    ELABORACAO = "elaboracao", "Em elaboração"
    REVISAO = "revisao", "Em revisão"
    EMITIDO = "emitido", "Emitido"
    ARQUIVADO = "arquivado", "Arquivado"


class EstudoClassificacao(models.Model):
    nome = models.CharField("Projeto", max_length=200)
    cliente = models.CharField("Cliente", max_length=200, blank=True)
    empresa = models.ForeignKey(
        "crm.Empresa",
        verbose_name="Empresa (CRM)",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estudos_classificacao",
    )
    revisao = models.CharField("Revisão", max_length=10, default="0")
    status = models.CharField("Status", max_length=12, choices=StatusEstudo.choices, default=StatusEstudo.ELABORACAO)
    estado = models.JSONField("Estado da calculadora", default=dict, blank=True)
    criado_por = models.ForeignKey(
        "funcionarios.Funcionario",
        verbose_name="Criado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estudos_classificacao_criados",
    )
    atualizado_por = models.ForeignKey(
        "funcionarios.Funcionario",
        verbose_name="Atualizado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estudos_classificacao_atualizados",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Estudo de classificação de áreas"
        verbose_name_plural = "Estudos de classificação de áreas"
        ordering = ["-atualizado_em"]

    def __str__(self) -> str:
        return f"{self.nome} (rev. {self.revisao})"

    # Resumo lido do JSON para a lista
    @property
    def fontes(self) -> list:
        return (self.estado or {}).get("fontes") or []

    @property
    def n_fontes(self) -> int:
        return len(self.fontes)

    @property
    def n_produtos(self) -> int:
        return len({f.get("pid") for f in self.fontes if f.get("pid")})
