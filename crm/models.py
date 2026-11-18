from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import models
from django.utils import timezone

from funcionarios.models import Funcionario

from .choices import ESTADOS_BR


class TipoLista(models.TextChoices):
    NICHO_MERCADOLOGICO = "nicho_mercadologico", "Nicho mercadológico"
    CLIENTES_RSC = "clientes_rsc", "Clientes RSC"


class ClassificacaoUnidade(models.TextChoices):
    FILIAL = "filial", "Filial"
    SEDE_CORPORATIVA = "sede_corporativa", "Sede corporativa"
    MATRIZ = "matriz", "Matriz"


class TipoSubfunil(models.TextChoices):
    PRE_VENDAS = "pre_vendas", "Pré-vendas"
    NEGOCIACOES = "negociacoes", "Negociações"
    POS_VENDAS = "pos_vendas", "Pós-vendas"


class FatorComissionamento(models.TextChoices):
    PASSIVO = "passivo", "Comissionamento passivo - 4,5%"
    ATIVO = "ativo", "Comissionamento ativo - 7,0%"
    GUARDA_CHUVA = "guarda_chuva", "Comissionamento guarda-chuva (MBRF) - 10,0%"


FATOR_COMISSIONAMENTO_PCT = {
    FatorComissionamento.PASSIVO: "4.5",
    FatorComissionamento.ATIVO: "7.0",
    FatorComissionamento.GUARDA_CHUVA: "10.0",
}


# Sequência fixa do fluxo comercial
ORDEM_TIPO_SUBFUNIL = {
    TipoSubfunil.PRE_VENDAS: 0,
    TipoSubfunil.NEGOCIACOES: 1,
    TipoSubfunil.POS_VENDAS: 2,
}


class ItemLista(models.Model):
    """Itens de listas usadas pelo sistema (ex.: nichos mercadológicos)."""

    tipo = models.CharField("Tipo da lista", max_length=40, choices=TipoLista.choices)
    nome = models.CharField("Nome", max_length=150)
    ativo = models.BooleanField("Ativo", default=True)
    ordem = models.PositiveIntegerField("Ordem", default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Item de lista"
        verbose_name_plural = "Itens de lista"
        ordering = ["tipo", "ordem", "nome"]
        unique_together = [("tipo", "nome")]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()}: {self.nome}"

    def funis_ativos(self):
        return self.funis.filter(ativo=True).order_by("ordem", "tipo")

    def funil_principal(self):
        return self.funis_ativos().first()


class Empresa(models.Model):
    nome = models.CharField("Nome da Empresa", max_length=200)
    site = models.URLField("Site da empresa", blank=True)
    nicho = models.ForeignKey(
        ItemLista,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="empresas_nicho",
        verbose_name="Nicho mercadológico",
        limit_choices_to={"tipo": TipoLista.NICHO_MERCADOLOGICO, "ativo": True},
    )
    classificacao_unidade = models.CharField(
        "Classificação da unidade",
        max_length=30,
        choices=ClassificacaoUnidade.choices,
        blank=True,
    )
    telefone_portaria = models.CharField("Telefone (Portaria)", max_length=30, blank=True)
    telefone_portaria_2 = models.CharField("Telefone 2 (Portaria)", max_length=30, blank=True)
    email_geral = models.EmailField("E-mail geral", blank=True)
    cidade = models.CharField("Cidade", max_length=120, blank=True)
    estado = models.CharField("Estado", max_length=2, choices=ESTADOS_BR, blank=True)
    clientes_rsc = models.ManyToManyField(
        ItemLista,
        blank=True,
        related_name="empresas_visiveis",
        verbose_name="Visível para clientes RSC",
        limit_choices_to={"tipo": TipoLista.CLIENTES_RSC, "ativo": True},
        help_text="Clientes externos que podem ver esta empresa. Funcionários RSC sempre veem tudo.",
    )
    # campos legados mantidos opcionais
    cnpj = models.CharField("CNPJ", max_length=18, blank=True)
    razao_social = models.CharField("Razão social", max_length=200, blank=True)
    nome_curto = models.CharField(
        "Nome curto",
        max_length=60,
        blank=True,
        help_text="Usado no nome do arquivo e da pasta da proposta (ex.: RME).",
    )
    logradouro = models.CharField("Logradouro e número", max_length=200, blank=True)
    complemento = models.CharField("Complemento / bairro", max_length=200, blank=True)
    cep = models.CharField("CEP", max_length=10, blank=True)
    pais = models.CharField("País", max_length=60, blank=True, default="Brasil")
    observacoes = models.TextField("Observações", blank=True)
    ativa = models.BooleanField("Ativa", default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Contato(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="contatos",
        verbose_name="Empresa",
        help_text="Empresa na qual o contato trabalha",
    )
    nome = models.CharField("Nome", max_length=100)
    sobrenome = models.CharField("Sobrenome", max_length=100, blank=True)
    email = models.EmailField("E-mail", blank=True)
    telefone_ramal = models.CharField("Telefone (Ramal)", max_length=30, blank=True)
    telefone_whatsapp = models.CharField("Telefone (WhatsApp)", max_length=30, blank=True)
    responsavel = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contatos_responsavel",
        verbose_name="Responsável pelo contato",
    )
    clientes_rsc = models.ManyToManyField(
        ItemLista,
        blank=True,
        related_name="contatos_visiveis",
        verbose_name="Visível para clientes RSC",
        limit_choices_to={"tipo": TipoLista.CLIENTES_RSC, "ativo": True},
        help_text="Clientes externos que podem ver este contato. Funcionários RSC sempre veem tudo.",
    )
    # legado
    cargo = models.CharField("Cargo", max_length=100, blank=True)
    principal = models.BooleanField(
        "Contato principal",
        default=False,
        help_text="Pré-selecionado nas propostas desta empresa.",
    )
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Contato"
        verbose_name_plural = "Contatos"
        ordering = ["nome", "sobrenome"]

    def __str__(self) -> str:
        return f"{self.nome_completo} ({self.empresa})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Um contato principal por empresa.
        if self.principal and self.empresa_id:
            Contato.objects.filter(empresa_id=self.empresa_id, principal=True).exclude(
                pk=self.pk
            ).update(principal=False)

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.sobrenome}".strip()


class Funil(models.Model):
    nome = models.CharField("Nome", max_length=120)
    descricao = models.TextField("Descrição", blank=True)
    cliente_rsc = models.ForeignKey(
        ItemLista,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="funis",
        verbose_name="Cliente RSC",
        limit_choices_to={"tipo": TipoLista.CLIENTES_RSC},
        help_text="Cliente RSC dono deste funil de controle.",
    )
    tipo = models.CharField(
        "Subfunil",
        max_length=20,
        choices=TipoSubfunil.choices,
        default=TipoSubfunil.PRE_VENDAS,
    )
    ordem = models.PositiveSmallIntegerField(
        "Ordem no fluxo",
        default=0,
        help_text="Sequência fixa: pré-vendas (0) → negociações (1) → pós-vendas (2).",
    )
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Carteira"
        verbose_name_plural = "Carteira"
        ordering = ["cliente_rsc__nome", "ordem", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente_rsc", "tipo"],
                condition=models.Q(cliente_rsc__isnull=False),
                name="uniq_funil_cliente_tipo",
            )
        ]

    def save(self, *args, **kwargs):
        self.ordem = ORDEM_TIPO_SUBFUNIL.get(self.tipo, 9)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.cliente_rsc_id:
            return f"{self.cliente_rsc.nome} · {self.get_tipo_display()}"
        return self.nome

    @property
    def rotulo_sidebar(self) -> str:
        return self.get_tipo_display()


class EtapaFunil(models.Model):
    funil = models.ForeignKey(
        Funil,
        on_delete=models.CASCADE,
        related_name="etapas",
        verbose_name="Funil",
    )
    nome = models.CharField("Nome", max_length=120)
    ordem = models.PositiveIntegerField("Ordem", default=0)

    class Meta:
        verbose_name = "Etapa do funil"
        verbose_name_plural = "Etapas do funil"
        ordering = ["funil", "ordem", "pk"]

    def __str__(self) -> str:
        return f"{self.funil} · {self.nome}"


class OrigemLead(models.TextChoices):
    LINKEDIN = "linkedin", "LinkedIn"
    INDICACAO = "indicacao", "Indicação"
    SITE = "site", "Site"
    COLD_CALL = "cold_call", "Cold call"
    EVENTO = "evento", "Evento"
    EMAIL = "email", "E-mail"
    OUTRO = "outro", "Outro"


class TemperaturaLead(models.TextChoices):
    QUENTE = "quente", "Quente"
    MORNO = "morno", "Morno"
    FRIO = "frio", "Frio"


class FormaContato(models.TextChoices):
    EMAIL = "email", "E-mail"
    TELEFONE = "telefone", "Telefone"
    WHATSAPP = "whatsapp", "WhatsApp"


class MotivoFaltaRetorno(models.TextChoices):
    NAO_DISPONIVEL = "nao_disponivel", "Não estava disponível"
    PORTARIA = "portaria", "Portaria não pode passar contato"
    LIGACAO = "ligacao", "Não completou a ligação"
    SEM_EMAIL = "sem_email", "Sem retorno de e-mail"


MAX_TERCEIROS = 5


def formatar_percentual(valor: Decimal) -> str:
    """18.00 → "18"; 16.50 → "16,5"."""
    return format(Decimal(valor).normalize(), "f").replace(".", ",")


class Oportunidade(models.Model):
    funil = models.ForeignKey(
        Funil,
        on_delete=models.CASCADE,
        related_name="oportunidades",
        verbose_name="Funil",
    )
    etapa = models.ForeignKey(
        EtapaFunil,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oportunidades",
        verbose_name="Etapa",
    )
    oportunidade_pai = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cards_filhos",
        verbose_name="Oportunidade origem",
        help_text="Card de Negociações que originou este acompanhamento em Pós-vendas.",
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="oportunidades",
        verbose_name="Empresa",
    )
    contato = models.ForeignKey(
        Contato,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oportunidades",
        verbose_name="Contato",
    )
    titulo = models.CharField("Título", max_length=200)
    valor = models.DecimalField(
        "Valor estimado",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    responsavel = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="oportunidades",
        verbose_name="Responsável",
    )
    # campos legados (mantidos vazios; preferir contato cadastrado)
    contato_nome = models.CharField("Nome do contato", max_length=150, blank=True)
    contato_email = models.EmailField("E-mail do contato", blank=True)
    contato_telefone = models.CharField("Telefone do contato", max_length=30, blank=True)
    origem = models.CharField(
        "Origem do lead",
        max_length=30,
        choices=OrigemLead.choices,
        blank=True,
    )
    temperatura = models.CharField(
        "Temperatura",
        max_length=20,
        choices=TemperaturaLead.choices,
        blank=True,
    )
    cidade = models.CharField("Cidade / local", max_length=120, blank=True)
    proxima_acao = models.CharField("Próxima ação", max_length=200, blank=True)
    data_retorno = models.DateField("Data de retorno", null=True, blank=True)
    data_reuniao = models.DateTimeField("Reunião agendada", null=True, blank=True)
    observacoes = models.TextField("Observações", blank=True)
    # formulário inicial (Pipefy Prospecção)
    contato_sucesso = models.BooleanField("Contato com sucesso?", null=True, blank=True)
    existe_demanda = models.BooleanField("Existe alguma demanda?", null=True, blank=True)
    dores_identificadas = models.TextField("Dores identificadas", blank=True)
    data_retorno_envio = models.DateField("Data de retorno / Envio", null=True, blank=True)
    # campos por etapa
    formas_contato = models.JSONField(
        "Formas de contato",
        default=list,
        blank=True,
        help_text="Canais usados no 1º Contato: e-mail, telefone, WhatsApp.",
    )
    motivo_falta_retorno = models.CharField(
        "Motivo da falta de retorno",
        max_length=40,
        choices=MotivoFaltaRetorno.choices,
        blank=True,
    )
    motivo_sem_oportunidade = models.TextField("Motivo da falta de oportunidade", blank=True)
    escopo_solicitado = models.TextField("Escopo solicitado", blank=True)
    funil_venda = models.ForeignKey(
        "Funil",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads_origem_pre_vendas",
        verbose_name="Funil de venda",
        help_text="Funil de negociação para o qual o lead será encaminhado ao concluir.",
    )
    # campos Negociações (Pipefy)
    proposta_arquivo = models.FileField(
        "Proposta enviada",
        upload_to="crm/propostas/%Y/%m/",
        blank=True,
    )
    proposta_internacional = models.BooleanField(
        "Proposta internacional?",
        null=True,
        blank=True,
    )
    data_contato_follow_up = models.DateField(
        "Nova data de contato",
        null=True,
        blank=True,
        help_text="Alerta de vencimento aparece 1 dia antes desta data.",
    )
    # Proposta Ganha
    valor_final_fechado = models.DecimalField(
        "Valor final fechado",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valor do negócio quando a proposta é ganha.",
    )
    desconto_concedido = models.DecimalField(
        "Desconto concedido",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fator_comissionamento = models.CharField(
        "Fator de comissionamento (legado)",
        max_length=20,
        choices=FatorComissionamento.choices,
        blank=True,
        help_text="Legado. Preferir percentual_comissao informado manualmente.",
    )
    percentual_comissao = models.DecimalField(
        "Percentual de comissão (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Informe o % de comissão sobre o valor final fechado.",
    )
    percentual_bonus = models.DecimalField(
        "Percentual de bônus do agente (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="De 12% a 35% da comissão, conforme performance.",
    )
    comissao = models.DecimalField(
        "Comissão",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Calculada: percentual × valor final fechado.",
    )
    bonus_agente = models.DecimalField(
        "Bônus para agente",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Calculado: percentual de bônus × comissão (12%–35%).",
    )
    # Proposta Ganha · custos do projeto
    custos_terceiros = models.JSONField(
        "Custos com terceiros",
        default=list,
        blank=True,
        help_text=f"Até {MAX_TERCEIROS} terceiros: lista de {{nome, valor}}.",
    )
    custo_viagem = models.DecimalField(
        "Custo com viagem",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    aliquota_impostos = models.DecimalField(
        "Alíquota de impostos (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Alíquota vigente quando a proposta foi ganha (Admin › Impostos).",
    )
    # Pós-vendas · Serviço finalizado
    atc_enviado = models.BooleanField("ATC enviado", default=False)
    atc_enviado_em = models.DateTimeField("ATC enviado em", null=True, blank=True)
    psc_enviado = models.BooleanField("PSC enviado", default=False)
    psc_enviado_em = models.DateTimeField("PSC enviado em", null=True, blank=True)
    retorno_recebido = models.BooleanField(
        "Retorno recebido",
        default=False,
        help_text="Se sim, o card vai para Pós-venda finalizado.",
    )
    retorno_recebido_em = models.DateTimeField("Retorno recebido em", null=True, blank=True)
    etapa_desde = models.DateTimeField("Nesta etapa desde", null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Oportunidade"
        verbose_name_plural = "Oportunidades"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return self.titulo

    def save(self, *args, **kwargs):
        if self.empresa_id and not self.titulo:
            partes = [self.empresa.nome]
            if self.empresa.cidade:
                loc = self.empresa.cidade
                if self.empresa.estado:
                    loc = f"{loc} ({self.empresa.estado})"
                partes.append(loc)
            self.titulo = " - ".join(partes)
        if self.empresa_id and not self.cidade:
            self.cidade = self.empresa.cidade
        super().save(*args, **kwargs)

    @property
    def contato_exibicao(self) -> str:
        if self.contato_id:
            return self.contato.nome_completo
        return self.contato_nome or "—"

    @property
    def email_exibicao(self) -> str:
        if self.contato_id and self.contato.email:
            return self.contato.email
        return self.contato_email or ""

    @property
    def telefone_exibicao(self) -> str:
        if self.contato_id:
            return self.contato.telefone_whatsapp or self.contato.telefone_ramal or ""
        return self.contato_telefone or ""

    @property
    def titulo_kanban(self) -> str:
        if self.empresa_id:
            partes = [self.empresa.nome]
            if self.empresa.cidade:
                loc = self.empresa.cidade
                if self.empresa.estado:
                    loc = f"{loc} ({self.empresa.estado})"
                partes.append(loc)
            return " - ".join(partes)
        return self.titulo

    @property
    def etapa_terminal(self) -> str:
        if not self.etapa_id:
            return ""
        nome = self.etapa.nome.lower()
        if "sem oportunidade" in nome:
            return "negativo"
        if "conclu" in nome:
            return "positivo"
        return ""

    @property
    def formas_contato_labels(self) -> list[str]:
        labels = dict(FormaContato.choices)
        valores = self.formas_contato or []
        if isinstance(valores, str):
            valores = [v.strip() for v in valores.split(",") if v.strip()]
        return [labels.get(v, v) for v in valores]

    @property
    def alerta_follow_up(self) -> str:
        """Retorna 'amanha', 'hoje' ou 'vencido' a partir de 1 dia antes da data."""
        if not self.data_contato_follow_up:
            return ""
        delta = (self.data_contato_follow_up - timezone.localdate()).days
        if delta > 1:
            return ""
        if delta == 1:
            return "amanha"
        if delta == 0:
            return "hoje"
        return "vencido"

    @property
    def alerta_follow_up_label(self) -> str:
        mapa = {
            "amanha": "Follow-up amanhã",
            "hoje": "Follow-up hoje",
            "vencido": "Follow-up vencido",
        }
        return mapa.get(self.alerta_follow_up, "")

    @property
    def valor_negocio(self):
        """Valor do negócio: final fechado quando ganha; senão valor da proposta."""
        if self.valor_final_fechado is not None:
            return self.valor_final_fechado
        return self.valor

    # ── Resultado financeiro (custos lançados na Proposta Ganha) ──
    @property
    def origem_custos(self) -> "Oportunidade":
        """Card filho de Pós-vendas usa os custos lançados no card de Negociações."""
        if self.oportunidade_pai_id and not self.custos_terceiros and self.custo_viagem is None:
            return self.oportunidade_pai
        return self

    @property
    def custos_terceiros_lista(self) -> list[dict]:
        itens = []
        for item in self.origem_custos.custos_terceiros or []:
            if not isinstance(item, dict):
                continue
            try:
                valor = Decimal(str(item.get("valor") or "0"))
            except (InvalidOperation, ValueError):
                valor = Decimal("0")
            nome = (item.get("nome") or "").strip()
            if nome or valor:
                itens.append({"nome": nome or "Terceiro", "valor": valor})
        return itens

    @property
    def custos_terceiros_form(self) -> list[dict]:
        """Sempre MAX_TERCEIROS linhas para o formulário da Proposta Ganha."""
        linhas = []
        for item in (self.custos_terceiros or [])[:MAX_TERCEIROS]:
            if isinstance(item, dict):
                linhas.append({"nome": item.get("nome") or "", "valor": item.get("valor")})
        while len(linhas) < MAX_TERCEIROS:
            linhas.append({"nome": "", "valor": None})
        return linhas

    @property
    def custo_terceiros_total(self) -> Decimal:
        return sum((i["valor"] for i in self.custos_terceiros_lista), Decimal("0"))

    @property
    def custo_viagem_efetivo(self) -> Decimal:
        return self.origem_custos.custo_viagem or Decimal("0")

    @property
    def custo_total(self) -> Decimal:
        return self.custo_terceiros_total + self.custo_viagem_efetivo

    @property
    def aliquota_efetiva(self) -> Decimal:
        """Alíquota gravada no negócio; sem ela, a vigente em Admin › Impostos."""
        if self.aliquota_impostos is not None:
            return self.aliquota_impostos
        if self.oportunidade_pai_id and self.oportunidade_pai.aliquota_impostos is not None:
            return self.oportunidade_pai.aliquota_impostos
        if not hasattr(self, "_aliquota_vigente"):
            from impostos.models import AliquotaImposto

            self._aliquota_vigente = AliquotaImposto.vigente()
        return self._aliquota_vigente

    @property
    def aliquota_efetiva_fmt(self) -> str:
        return formatar_percentual(self.aliquota_efetiva)

    @property
    def impostos(self) -> Decimal:
        valor = self.valor_negocio or Decimal("0")
        return (valor * self.aliquota_efetiva / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def comissao_efetiva(self) -> Decimal:
        if self.comissao is not None:
            return self.comissao
        if self.oportunidade_pai_id and self.oportunidade_pai.comissao is not None:
            return self.oportunidade_pai.comissao
        return Decimal("0")

    @property
    def bonus_agente_efetivo(self) -> Decimal:
        if self.bonus_agente is not None:
            return self.bonus_agente
        if self.oportunidade_pai_id and self.oportunidade_pai.bonus_agente is not None:
            return self.oportunidade_pai.bonus_agente
        return Decimal("0")

    @property
    def comissoes_total(self) -> Decimal:
        return self.comissao_efetiva + self.bonus_agente_efetivo

    @property
    def lucro_liquido(self) -> Decimal:
        """Valor − custos (terceiros + viagem) − impostos − comissão − bônus."""
        valor = self.valor_negocio or Decimal("0")
        return valor - self.custo_total - self.impostos - self.comissoes_total


class TipoHistoricoOpp(models.TextChoices):
    CRIADO = "criado", "Criado"
    ETAPA = "etapa", "Mudança de etapa"
    NOTA = "nota", "Nota"
    ATUALIZADO = "atualizado", "Atualizado"


class HistoricoOportunidade(models.Model):
    oportunidade = models.ForeignKey(
        Oportunidade,
        on_delete=models.CASCADE,
        related_name="historico",
        verbose_name="Oportunidade",
    )
    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=TipoHistoricoOpp.choices,
        default=TipoHistoricoOpp.NOTA,
    )
    descricao = models.TextField("Descrição")
    etapa_de = models.ForeignKey(
        EtapaFunil,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Etapa anterior",
    )
    etapa_para = models.ForeignKey(
        EtapaFunil,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Etapa nova",
    )
    autor = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_oportunidade",
        verbose_name="Autor",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Histórico da oportunidade"
        verbose_name_plural = "Históricos das oportunidades"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"{self.oportunidade} · {self.get_tipo_display()}"


class GmailVinculo(models.Model):
    """OAuth Gmail por usuário — independente do Google Calendar."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gmail_vinculo",
        verbose_name="Usuário",
    )
    email = models.EmailField("E-mail Google", blank=True)
    token = models.TextField("Access token")
    refresh_token = models.TextField("Refresh token", blank=True)
    token_uri = models.CharField(
        max_length=255, default="https://oauth2.googleapis.com/token"
    )
    client_id = models.CharField(max_length=255, blank=True)
    client_secret = models.CharField(max_length=255, blank=True)
    scopes = models.TextField(blank=True)
    expiry = models.DateTimeField(null=True, blank=True)
    conectado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vínculo Gmail"
        verbose_name_plural = "Vínculos Gmail"

    def __str__(self) -> str:
        return self.email or f"Gmail de {self.usuario}"

    @property
    def conectado(self) -> bool:
        return bool(self.refresh_token or self.token)
