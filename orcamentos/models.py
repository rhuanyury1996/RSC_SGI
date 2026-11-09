from django.db import models

from crm.models import Contato, Empresa
from funcionarios.models import Funcionario


class TabelaParametros(models.Model):
    """Parâmetros de preço de um ano (mesmo formato do parametros_2026.json)."""

    ano = models.PositiveSmallIntegerField("Ano da tabela", unique=True)
    dados = models.JSONField("Parâmetros")
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        Funcionario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Tabela de parâmetros"
        verbose_name_plural = "Tabelas de parâmetros"
        ordering = ["-ano"]

    def __str__(self) -> str:
        return f"{self.ano} · {self.dados.get('versao_tabela', '')}"

    def parametros(self):
        from .gexcon.parametros import Parametros

        return Parametros.de_dict(self.dados)


class Escopo(models.TextChoices):
    ER = "E&R", "EFFECTS + RISKCURVES"
    E = "E", "Só EFFECTS"


class TipoCliente(models.TextChoices):
    NOVO = "novo", "Cliente novo"
    RENOVACAO = "renovacao", "Renovação"


class StatusOrcamento(models.TextChoices):
    EMITIDA = "emitida", "Emitida"
    ENVIADA = "enviada", "Enviada"
    ACEITA = "aceita", "Aceita"
    RECUSADA = "recusada", "Recusada"


class Orcamento(models.Model):
    """Proposta emitida. Guarda o snapshot dos valores calculados e o .docx."""

    numero = models.CharField("Número", max_length=20, unique=True)
    data = models.DateField("Data da proposta", db_index=True)
    sequencial = models.PositiveSmallIntegerField("Sequencial do dia")
    validade = models.DateField("Validade")
    empresa = models.ForeignKey(
        Empresa, on_delete=models.SET_NULL, null=True, related_name="orcamentos"
    )
    contato = models.ForeignKey(
        Contato, on_delete=models.SET_NULL, null=True, blank=True, related_name="orcamentos"
    )
    cliente = models.JSONField("Cliente (snapshot)")
    contato_dados = models.JSONField("Contato (snapshot)")
    escopo = models.CharField("Escopo", max_length=3, choices=Escopo.choices)
    periodos = models.JSONField("Períodos (meses)")
    incluir_adicional = models.BooleanField("Usuário adicional", default=True)
    tipo_cliente_solicitado = models.CharField(max_length=10, choices=TipoCliente.choices)
    tipo_cliente_efetivo = models.CharField(max_length=10, choices=TipoCliente.choices)
    vencimento_licenca = models.DateField("Vencimento da licença atual", null=True, blank=True)
    categoria_licenca = models.CharField("Categoria de licença", max_length=20, default="comercial")
    desconto = models.DecimalField("Desconto da categoria", max_digits=5, decimal_places=4, default=0)
    unidades = models.PositiveSmallIntegerField("Licenças por módulo", default=1)
    dongles = models.PositiveSmallIntegerField("Dongles", default=0)
    linhas_software = models.JSONField("Linhas de software")
    treinamentos = models.JSONField("Treinamentos", default=list, blank=True)
    total_treinamentos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_servicos = models.DecimalField(max_digits=12, decimal_places=2)
    avisos = models.JSONField(default=list, blank=True)
    tabela = models.ForeignKey(TabelaParametros, on_delete=models.PROTECT, related_name="orcamentos")
    versao_tabela = models.CharField(max_length=120)
    nome_arquivo = models.CharField(max_length=200)
    arquivo = models.BinaryField("Arquivo .docx")
    emitido_por = models.ForeignKey(
        Funcionario, on_delete=models.SET_NULL, null=True, related_name="orcamentos_emitidos"
    )
    status = models.CharField(
        max_length=10, choices=StatusOrcamento.choices, default=StatusOrcamento.EMITIDA, db_index=True
    )
    historico_status = models.JSONField(default=list, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    # Campos da revisão de propostas (migração 0002_revisao_e_historico_edicoes)
    revisao = models.PositiveSmallIntegerField("Revisão", default=0)
    historico_edicoes = models.JSONField("Histórico de edições", default=list, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orçamento GEXCON"
        verbose_name_plural = "Orçamentos GEXCON"
        ordering = ["-data", "-sequencial"]

    def __str__(self) -> str:
        return self.numero
