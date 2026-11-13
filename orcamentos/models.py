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


# ------------------------------------------------------------------ RAVEN


class TipoClienteRaven(models.TextChoices):
    INDUSTRIA = "industria", "Indústria"
    CONSULTORIA = "consultoria", "Consultoria"


class PagamentoRaven(models.TextChoices):
    VISTA = "vista", "À vista (8% de desconto na licença)"
    BOLETO = "10x", "Parcelado em 10× no boleto"


class TabelaRaven(models.Model):
    """Planos e preços RAVEN de um ano (mesmo formato do raven/parametros_2026.json)."""

    ano = models.PositiveSmallIntegerField("Ano da tabela", unique=True)
    dados = models.JSONField("Parâmetros")
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        Funcionario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "Tabela RAVEN"
        verbose_name_plural = "Tabelas RAVEN"
        ordering = ["-ano"]

    def __str__(self) -> str:
        return f"{self.ano} · {self.dados.get('versao_tabela', '')}"

    def parametros(self):
        from .raven.calculo import ParametrosRaven

        return ParametrosRaven.de_dict(self.dados)


class OrcamentoRaven(models.Model):
    """Proposta RAVEN emitida. Guarda o snapshot dos valores e o HTML da proposta."""

    numero = models.CharField("Número", max_length=20, unique=True)
    data = models.DateField("Data da proposta", db_index=True)
    sequencial = models.PositiveSmallIntegerField("Sequencial do dia")
    validade = models.DateField("Validade")
    validade_dias = models.PositiveSmallIntegerField("Validade (dias)", default=30)
    empresa = models.ForeignKey(
        Empresa, on_delete=models.SET_NULL, null=True, related_name="orcamentos_raven"
    )
    contato = models.ForeignKey(
        Contato, on_delete=models.SET_NULL, null=True, blank=True, related_name="orcamentos_raven"
    )
    cliente = models.JSONField("Cliente (snapshot)")
    contato_dados = models.JSONField("Contato (snapshot)")
    tipo_cliente = models.CharField("Tipo de cliente", max_length=12, choices=TipoClienteRaven.choices)
    plano = models.CharField("Plano", max_length=30)
    plano_nome = models.CharField("Nome do plano", max_length=60)
    usuarios = models.PositiveSmallIntegerField("Usuários simultâneos", default=0)
    vigencia_meses = models.PositiveSmallIntegerField("Vigência (meses)", default=0)
    trial = models.BooleanField("Trial", default=False)
    valor_licenca = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_tabela = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    implantacao = models.BooleanField("Implantação em campo", default=False)
    valor_implantacao = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    horas_visita = models.PositiveSmallIntegerField(null=True, blank=True)
    cidade_visita = models.CharField("Cidade/UF da visita", max_length=120, blank=True)
    horas_pacote = models.PositiveIntegerField("Pacote de horas", default=0)
    valor_hora = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valor_pacote = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pagamento = models.CharField("Pagamento", max_length=6, choices=PagamentoRaven.choices, default=PagamentoRaven.VISTA)
    desconto = models.DecimalField("Desconto à vista", max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField("Total", max_digits=12, decimal_places=2)
    linhas = models.JSONField("Linhas da proposta", default=list)
    avisos = models.JSONField(default=list, blank=True)
    tabela = models.ForeignKey(TabelaRaven, on_delete=models.PROTECT, related_name="orcamentos")
    versao_tabela = models.CharField(max_length=120)
    nome_arquivo = models.CharField(max_length=200)
    arquivo = models.BinaryField("Proposta (.html)")
    emitido_por = models.ForeignKey(
        Funcionario, on_delete=models.SET_NULL, null=True, related_name="orcamentos_raven_emitidos"
    )
    status = models.CharField(
        max_length=10, choices=StatusOrcamento.choices, default=StatusOrcamento.EMITIDA, db_index=True
    )
    historico_status = models.JSONField(default=list, blank=True)
    aceite_em = models.DateTimeField("Aceite em", null=True, blank=True)
    login_liberado_em = models.DateTimeField("Login liberado em", null=True, blank=True)
    login_liberado_por = models.ForeignKey(
        Funcionario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Orçamento RAVEN"
        verbose_name_plural = "Orçamentos RAVEN"
        ordering = ["-data", "-sequencial"]

    def __str__(self) -> str:
        return self.numero

    @property
    def prazo_login(self):
        """Aceite + 48 h (prazo prometido na proposta para liberar o login)."""
        if not self.aceite_em:
            return None
        from datetime import timedelta

        horas = 48
        try:
            horas = int(self.tabela.dados.get("prazo_login_horas", 48))
        except (AttributeError, TypeError, ValueError):
            pass
        return self.aceite_em + timedelta(hours=horas)

    @property
    def aguardando_login(self) -> bool:
        return self.status == StatusOrcamento.ACEITA and self.login_liberado_em is None
