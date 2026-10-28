import re
from decimal import Decimal

from django.conf import settings
from django.db.models import (
    Count,
    DecimalField,
    OuterRef,
    Prefetch,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from funcionarios.models import Funcionario

from .models import (
    ORDEM_TIPO_SUBFUNIL,
    Contato,
    Empresa,
    EtapaFunil,
    FormaContato,
    Funil,
    HistoricoOportunidade,
    ItemLista,
    Oportunidade,
    OrigemLead,
    TipoHistoricoOpp,
    TipoLista,
    TipoSubfunil,
)

# Alinhado a Oportunidade.valor_negocio (final fechado, senão valor da proposta).
_DECIMAL_VALOR = DecimalField(max_digits=12, decimal_places=2)
_DECIMAL_PIPELINE = DecimalField(max_digits=14, decimal_places=2)


def _expr_valor_negocio():
    return Coalesce("valor_final_fechado", "valor", output_field=_DECIMAL_VALOR)


def soma_pipeline_qs(qs) -> Decimal:
    """Soma o valor de negócio das oportunidades do queryset."""
    total = qs.aggregate(total=Sum(_expr_valor_negocio()))["total"]
    return total if total is not None else Decimal("0")

ETAPAS_POR_TIPO = {
    # Fluxo real de Prospecção (Pipefy → kanban SGI)
    TipoSubfunil.PRE_VENDAS: (
        "Captura",
        "1º Contato",
        "Retornar contato",
        "Envio de material | Reunião",
        "Follow Up",
        "Sem oportunidade",
        "Concluído",
    ),
    # Fluxo real de Negociações (Pipefy → kanban SGI)
    TipoSubfunil.NEGOCIACOES: (
        "Oportunidade confirmada",
        "Elaborando proposta",
        "Proposta enviada",
        "Follow Up",
        "Aguardando desfecho",
        "Proposta Perdida",
        "Proposta Ganha",
    ),
    # Fluxo real de Pós-vendas (acompanhamento do card ganho)
    TipoSubfunil.POS_VENDAS: (
        "Acompanhando serviço",
        "Serviço finalizado",
        "Pós-venda finalizado",
        "Upsell",
        "Renovação",
    ),
}

# legado (funis sem tipo específico)
ETAPAS_PADRAO = ETAPAS_POR_TIPO[TipoSubfunil.NEGOCIACOES]

# sequência fixa do fluxo
SEQUENCIA_SUBFUNIS = (
    TipoSubfunil.PRE_VENDAS,
    TipoSubfunil.NEGOCIACOES,
    TipoSubfunil.POS_VENDAS,
)

# renomeações ao migrar etapas antigas de pré-vendas
RENOMEAR_ETAPAS_PRE_VENDAS = {
    "Lead": "Captura",
    "Contato inicial": "1º Contato",
    "Qualificação": "1º Contato",
    "Agendamento": "Envio de material | Reunião",
    "Agendar reunião": "Envio de material | Reunião",
    "Stand-by": "Follow Up",
    "Sem oportunidade no momento ou solicitada proposta": "Sem oportunidade",
}

RENOMEAR_ETAPAS_NEGOCIACOES = {
    "Proposta": "Oportunidade confirmada",
    "Proposta solicitada": "Oportunidade confirmada",
    "Negociação": "Elaborando proposta",
    "Contrato": "Proposta enviada",
    "Fechamento": "Proposta Ganha",
}

DESCRICOES_ETAPAS_PRE_VENDAS = {
    "Captura": "Aqui chegam os cards criados no formulário inicial.",
    "1º Contato": "Primeiro contato com o lead / empresa.",
    "Retornar contato": "Aguardando ou reagendando retorno de contato.",
    "Envio de material | Reunião": "Material enviado e/ou reunião marcada.",
    "Follow Up": "Acompanhamento até haver (ou não) oportunidade.",
    "Sem oportunidade": "Lead sem oportunidade no momento.",
    "Concluído": "Lead qualificado e pronto para Negociações.",
}

DESCRICOES_ETAPAS_NEGOCIACOES = {
    "Oportunidade confirmada": (
        "Quando a oportunidade realmente é confirmada ela entra nesta fase "
        "para evoluirmos com a proposta"
    ),
    "Elaborando proposta": "Essa fase indica que a proposta está sendo elaborada",
    "Proposta enviada": (
        "Enviamos a proposta, agora temos que definir a estratégia de contato."
    ),
    "Follow Up": "Devemos fazer o acompanhamento do contato.",
}

RENOMEAR_ETAPAS_POS_VENDAS = {
    "Onboarding": "Acompanhando serviço",
    "Acompanhamento": "Acompanhando serviço",
}

DESCRICOES_ETAPAS_POS_VENDAS = {
    "Acompanhando serviço": "Acompanhamento do serviço contratado após a proposta ganha.",
    "Serviço finalizado": (
        "Marque o envio de ATC e PSC e o retorno. Com retorno recebido, "
        "o card vai para Pós-venda finalizado."
    ),
    "Pós-venda finalizado": "Pós-venda concluída após ATC/PSC e retorno confirmado.",
    "Upsell": "Oportunidade de expansão / upsell.",
    "Renovação": "Renovação do contrato ou serviço.",
}


def garantir_etapas_padrao(funil: Funil) -> None:
    nomes = ETAPAS_POR_TIPO.get(funil.tipo, ETAPAS_PADRAO)

    if funil.tipo == TipoSubfunil.PRE_VENDAS:
        _sincronizar_etapas_pre_vendas(funil, nomes)
        return

    if funil.tipo == TipoSubfunil.NEGOCIACOES:
        _sincronizar_etapas_negociacoes(funil, nomes)
        return

    if funil.tipo == TipoSubfunil.POS_VENDAS:
        _sincronizar_etapas_pos_vendas(funil, nomes)
        return

    if funil.etapas.exists():
        return
    EtapaFunil.objects.bulk_create(
        [EtapaFunil(funil=funil, nome=nome, ordem=idx) for idx, nome in enumerate(nomes)]
    )


def _sincronizar_etapas_pos_vendas(funil: Funil, nomes: tuple[str, ...]) -> None:
    for antigo, novo in RENOMEAR_ETAPAS_POS_VENDAS.items():
        EtapaFunil.objects.filter(funil=funil, nome=antigo).exclude(nome__in=nomes).update(
            nome=novo
        )

    existentes = {e.nome: e for e in funil.etapas.all()}
    oficiais = set(nomes)
    for idx, nome in enumerate(nomes):
        etapa = existentes.pop(nome, None)
        if etapa is None:
            EtapaFunil.objects.create(funil=funil, nome=nome, ordem=idx)
        elif etapa.ordem != idx:
            etapa.ordem = idx
            etapa.save(update_fields=["ordem"])

    for etapa in existentes.values():
        if etapa.nome in oficiais:
            continue
        if not etapa.oportunidades.exists():
            etapa.delete()


def css_coluna_pos_vendas(nome: str) -> str:
    n = (nome or "").lower()
    if "pós-venda finalizado" in n or "pos-venda finalizado" in n:
        return "col-ganha"
    if "serviço finalizado" in n or "servico finalizado" in n:
        return "col-positivo"
    if "upsell" in n:
        return "col-roxo"
    if "renova" in n:
        return "col-teal"
    return "col-neutro"


def fase_campos_pos_vendas(etapa_nome: str) -> str:
    n = (etapa_nome or "").lower()
    if "serviço finalizado" in n or "servico finalizado" in n:
        return "servico_finalizado"
    if "pós-venda finalizado" in n or "pos-venda finalizado" in n:
        return "pos_venda_finalizado"
    if "upsell" in n:
        return "upsell"
    if "renova" in n:
        return "renovacao"
    if "acompanhando" in n:
        return "acompanhando"
    return "geral"


def _sincronizar_etapas_negociacoes(funil: Funil, nomes: tuple[str, ...]) -> None:
    for antigo, novo in RENOMEAR_ETAPAS_NEGOCIACOES.items():
        EtapaFunil.objects.filter(funil=funil, nome=antigo).exclude(nome__in=nomes).update(
            nome=novo
        )

    existentes = {e.nome: e for e in funil.etapas.all()}
    oficiais = set(nomes)
    for idx, nome in enumerate(nomes):
        etapa = existentes.pop(nome, None)
        if etapa is None:
            EtapaFunil.objects.create(funil=funil, nome=nome, ordem=idx)
        elif etapa.ordem != idx:
            etapa.ordem = idx
            etapa.save(update_fields=["ordem"])

    for etapa in existentes.values():
        if etapa.nome in oficiais:
            continue
        if not etapa.oportunidades.exists():
            etapa.delete()


def css_coluna_negociacoes(nome: str) -> str:
    n = (nome or "").lower()
    if "perdida" in n:
        return "col-negativo"
    if "ganha" in n:
        return "col-ganha"
    if "aguardando" in n:
        return "col-neutro"
    if "enviada" in n or n.startswith("follow"):
        return "col-roxo"
    return "col-teal"


def css_coluna_pre_vendas(nome: str) -> str:
    """Mesmo padrão visual de Negociações: faixa colorida + destaque no fim do fluxo."""
    n = (nome or "").lower()
    if "sem oportunidade" in n:
        return "col-negativo"
    if "conclu" in n:
        return "col-ganha"
    if n.startswith("follow"):
        return "col-roxo"
    if "envio" in n or "reuni" in n:
        return "col-neutro"
    return "col-teal"


def _sincronizar_etapas_pre_vendas(funil: Funil, nomes: tuple[str, ...]) -> None:
    for antigo, novo in RENOMEAR_ETAPAS_PRE_VENDAS.items():
        EtapaFunil.objects.filter(funil=funil, nome=antigo).exclude(
            nome__in=nomes
        ).update(nome=novo)

    # merge nomes parcialmente iguais (ex.: "Envio de material | Reunião...")
    for etapa in funil.etapas.exclude(nome__in=nomes):
        for oficial in nomes:
            if etapa.nome.startswith(oficial[:18]) or oficial.startswith(etapa.nome[:18]):
                if not funil.etapas.filter(nome=oficial).exclude(pk=etapa.pk).exists():
                    etapa.nome = oficial
                    etapa.save(update_fields=["nome"])
                break

    existentes = {e.nome: e for e in funil.etapas.all()}
    oficiais = set(nomes)
    captura = None

    for idx, nome in enumerate(nomes):
        etapa = existentes.pop(nome, None)
        if etapa is None:
            etapa = EtapaFunil.objects.create(funil=funil, nome=nome, ordem=idx)
        elif etapa.ordem != idx:
            etapa.ordem = idx
            etapa.save(update_fields=["ordem"])
        if nome == "Captura":
            captura = etapa

    # etapas legadas com cards: move para Captura e remove
    for etapa in list(existentes.values()):
        if etapa.nome in oficiais:
            continue
        if etapa.oportunidades.exists() and captura:
            etapa.oportunidades.update(etapa=captura)
        etapa.delete()


def _nome_subfunil(cliente: ItemLista, tipo: str) -> str:
    label = dict(TipoSubfunil.choices).get(tipo, tipo)
    return f"{cliente.nome} · {label}"


def garantir_funis_para_cliente(cliente: ItemLista) -> list[Funil]:
    """Garante os 3 subfunis na ordem pré → negociação → pós."""
    if cliente.tipo != TipoLista.CLIENTES_RSC:
        return []

    criados_ou_atualizados: list[Funil] = []
    for tipo in SEQUENCIA_SUBFUNIS:
        funil, _created = Funil.objects.get_or_create(
            cliente_rsc=cliente,
            tipo=tipo,
            defaults={
                "nome": _nome_subfunil(cliente, tipo),
                "descricao": f"{dict(TipoSubfunil.choices)[tipo]} — {cliente.nome}",
                "ativo": cliente.ativo,
                "ordem": ORDEM_TIPO_SUBFUNIL[tipo],
            },
        )
        updates: list[str] = []
        nome_esperado = _nome_subfunil(cliente, tipo)
        ordem_esperada = ORDEM_TIPO_SUBFUNIL[tipo]
        if funil.nome != nome_esperado:
            funil.nome = nome_esperado
            updates.append("nome")
        if funil.ordem != ordem_esperada:
            funil.ordem = ordem_esperada
            updates.append("ordem")
        if funil.ativo != cliente.ativo:
            funil.ativo = cliente.ativo
            updates.append("ativo")
        if updates:
            funil.save(update_fields=updates)
        garantir_etapas_padrao(funil)
        criados_ou_atualizados.append(funil)

    return criados_ou_atualizados


def garantir_funil_para_cliente(cliente: ItemLista) -> Funil | None:
    funis = garantir_funis_para_cliente(cliente)
    return funis[0] if funis else None


def registrar_historico(
    oportunidade: Oportunidade,
    *,
    tipo: str,
    descricao: str,
    autor=None,
    etapa_de: EtapaFunil | None = None,
    etapa_para: EtapaFunil | None = None,
) -> HistoricoOportunidade:
    return HistoricoOportunidade.objects.create(
        oportunidade=oportunidade,
        tipo=tipo,
        descricao=descricao,
        autor=autor,
        etapa_de=etapa_de,
        etapa_para=etapa_para,
    )


def mover_oportunidade(
    oportunidade: Oportunidade,
    nova_etapa: EtapaFunil,
    *,
    autor=None,
) -> Oportunidade:
    etapa_antiga = oportunidade.etapa
    if etapa_antiga and etapa_antiga.pk == nova_etapa.pk:
        return oportunidade

    oportunidade.etapa = nova_etapa
    oportunidade.etapa_desde = timezone.now()
    oportunidade.save(update_fields=["etapa", "etapa_desde", "atualizado_em"])

    de_nome = etapa_antiga.nome if etapa_antiga else "—"
    registrar_historico(
        oportunidade,
        tipo=TipoHistoricoOpp.ETAPA,
        descricao=f"Etapa: {de_nome} → {nova_etapa.nome}",
        autor=autor,
        etapa_de=etapa_antiga,
        etapa_para=nova_etapa,
    )

    # Concluído em pré-vendas → Negociações · Oportunidade confirmada
    if (
        oportunidade.funil.tipo == TipoSubfunil.PRE_VENDAS
        and "conclu" in (nova_etapa.nome or "").lower()
    ):
        return promover_para_negociacoes(oportunidade, autor=autor)

    # Proposta Ganha → cria card filho em Pós-vendas (acompanhamento)
    if (
        oportunidade.funil.tipo == TipoSubfunil.NEGOCIACOES
        and "ganha" in (nova_etapa.nome or "").lower()
    ):
        criar_card_pos_vendas(oportunidade, autor=autor)

    return oportunidade


def criar_card_pos_vendas(oportunidade: Oportunidade, *, autor=None) -> Oportunidade | None:
    """Cria card filho em Pós-vendas a partir da proposta ganha (não remove o pai)."""
    if oportunidade.funil.tipo != TipoSubfunil.NEGOCIACOES:
        return None
    if not oportunidade.funil.cliente_rsc_id:
        return None

    existente = (
        Oportunidade.objects.filter(
            oportunidade_pai=oportunidade,
            funil__tipo=TipoSubfunil.POS_VENDAS,
        )
        .select_related("funil", "etapa")
        .first()
    )
    if existente:
        return existente

    funis = garantir_funis_para_cliente(oportunidade.funil.cliente_rsc)
    funil_pos = next((f for f in funis if f.tipo == TipoSubfunil.POS_VENDAS), None)
    if funil_pos is None:
        return None

    garantir_etapas_padrao(funil_pos)
    etapa = (
        funil_pos.etapas.filter(nome="Acompanhando serviço").first()
        or funil_pos.etapas.order_by("ordem", "pk").first()
    )
    if etapa is None:
        return None

    valor = oportunidade.valor_negocio
    filho = Oportunidade.objects.create(
        funil=funil_pos,
        etapa=etapa,
        empresa=oportunidade.empresa,
        contato=oportunidade.contato,
        titulo=f"{oportunidade.titulo_kanban} · Acompanhamento",
        valor=valor,
        responsavel=oportunidade.responsavel,
        cidade=oportunidade.cidade,
        escopo_solicitado=oportunidade.escopo_solicitado,
        valor_final_fechado=oportunidade.valor_final_fechado,
        oportunidade_pai=oportunidade,
        etapa_desde=timezone.now(),
    )
    registrar_historico(
        filho,
        tipo=TipoHistoricoOpp.CRIADO,
        descricao=(
            f"Card filho criado a partir de Negociações · {oportunidade.etapa.nome if oportunidade.etapa else 'Proposta Ganha'} "
            f"(#{oportunidade.pk})."
        ),
        autor=autor,
        etapa_para=etapa,
    )
    registrar_historico(
        oportunidade,
        tipo=TipoHistoricoOpp.ATUALIZADO,
        descricao=f"Card de pós-vendas criado para acompanhamento (#{filho.pk}).",
        autor=autor,
    )
    return filho


def promover_para_negociacoes(oportunidade: Oportunidade, *, autor=None) -> Oportunidade:
    """Leva o card concluído de pré-vendas para Negociações · Oportunidade confirmada."""
    funil_origem = oportunidade.funil
    if funil_origem.tipo != TipoSubfunil.PRE_VENDAS or not funil_origem.cliente_rsc_id:
        return oportunidade

    funis = garantir_funis_para_cliente(funil_origem.cliente_rsc)
    funil_neg = next((f for f in funis if f.tipo == TipoSubfunil.NEGOCIACOES), None)
    if funil_neg is None:
        return oportunidade

    garantir_etapas_padrao(funil_neg)
    etapa_destino = (
        funil_neg.etapas.filter(nome="Oportunidade confirmada").first()
        or funil_neg.etapas.order_by("ordem", "pk").first()
    )
    if etapa_destino is None:
        return oportunidade

    etapa_de = oportunidade.etapa
    oportunidade.funil = funil_neg
    oportunidade.etapa = etapa_destino
    oportunidade.funil_venda = funil_neg
    oportunidade.etapa_desde = timezone.now()
    oportunidade.save(
        update_fields=[
            "funil",
            "etapa",
            "funil_venda",
            "etapa_desde",
            "atualizado_em",
        ]
    )
    registrar_historico(
        oportunidade,
        tipo=TipoHistoricoOpp.ETAPA,
        descricao=(
            f"Encaminhado de Pré-vendas (Concluído) para Negociações · {etapa_destino.nome}."
            + (
                f" Escopo: {oportunidade.escopo_solicitado[:180]}"
                if oportunidade.escopo_solicitado
                else ""
            )
        ),
        autor=autor,
        etapa_de=etapa_de,
        etapa_para=etapa_destino,
    )
    return oportunidade


def tempo_na_etapa(oportunidade: Oportunidade) -> str:
    inicio = oportunidade.etapa_desde or oportunidade.criado_em
    if not inicio:
        return ""
    delta = timezone.now() - inicio
    minutos = int(delta.total_seconds() // 60)
    if minutos < 60:
        return f"{max(minutos, 0)} min"
    horas = minutos // 60
    if horas < 48:
        return f"{horas} h"
    return f"{horas // 24} d"


def sincronizar_funis_clientes() -> int:
    antes = Funil.objects.count()
    for cliente in ItemLista.objects.filter(tipo=TipoLista.CLIENTES_RSC):
        garantir_funis_para_cliente(cliente)
    return Funil.objects.count() - antes


def metricas_comerciais() -> dict:
    ops = Oportunidade.objects.select_related("empresa", "etapa", "funil", "responsavel")
    total_ops = ops.count()
    pipeline = soma_pipeline_qs(ops)
    por_etapa = (
        ops.values("etapa__nome")
        .annotate(qtd=Count("id"), soma=Sum(_expr_valor_negocio()))
        .order_by("etapa__ordem", "etapa__nome")
    )
    recentes = list(ops.order_by("-criado_em")[:8])
    return {
        "total_oportunidades": total_ops,
        "pipeline_valor": pipeline,
        "por_etapa": list(por_etapa),
        "recentes": recentes,
    }


def funis_com_contagens():
    # Subquery evita o produto cartesiano etapas × oportunidades que inflava
    # Sum("oportunidades__valor") quando Count("etapas") entra no mesmo annotate.
    pipeline_sq = (
        Oportunidade.objects.filter(funil_id=OuterRef("pk"))
        .order_by()
        .values("funil_id")
        .annotate(total=Sum(_expr_valor_negocio()))
        .values("total")[:1]
    )
    return (
        Funil.objects.filter(ativo=True)
        .select_related("cliente_rsc")
        .annotate(
            total_etapas=Count("etapas", distinct=True),
            total_ops=Count("oportunidades", distinct=True),
            pipeline=Coalesce(
                Subquery(pipeline_sq, output_field=_DECIMAL_PIPELINE),
                Value(Decimal("0.00")),
                output_field=_DECIMAL_PIPELINE,
            ),
        )
        .prefetch_related(
            Prefetch("etapas", queryset=EtapaFunil.objects.order_by("ordem", "nome"))
        )
        .order_by("cliente_rsc__nome", "ordem", "nome")
    )


def funis_agrupados_por_cliente():
    funis = list(funis_com_contagens().filter(cliente_rsc__isnull=False))
    grupos: dict[int, dict] = {}
    ordem_clientes: list[int] = []
    for funil in funis:
        cid = funil.cliente_rsc_id
        if cid not in grupos:
            grupos[cid] = {"cliente": funil.cliente_rsc, "funis": []}
            ordem_clientes.append(cid)
        grupos[cid]["funis"].append(funil)
    return [grupos[cid] for cid in ordem_clientes]


def nav_funis_sidebar(funil_ativo_id: int | None = None) -> list[dict]:
    funis = (
        Funil.objects.filter(ativo=True, cliente_rsc__isnull=False, cliente_rsc__ativo=True)
        .select_related("cliente_rsc")
        .order_by("cliente_rsc__nome", "ordem")
    )
    grupos: dict[int, dict] = {}
    ordem: list[int] = []
    for funil in funis:
        cid = funil.cliente_rsc_id
        if cid not in grupos:
            grupos[cid] = {
                "cliente": funil.cliente_rsc,
                "funis": [],
                "aberto": False,
            }
            ordem.append(cid)
        grupos[cid]["funis"].append(funil)
        if funil_ativo_id and funil.pk == funil_ativo_id:
            grupos[cid]["aberto"] = True
    return [grupos[i] for i in ordem]


_EMPRESA_BODY_PATTERNS = (
    re.compile(
        r"(?:nós e a|nós e o|entre nós e a|entre nós e o|com a empresa|com a|com o)\s+"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*){0,3})",
        re.IGNORECASE,
    ),
    re.compile(
        r"empresa\s+([A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÜ][\w\-]*){0,3})",
        re.IGNORECASE,
    ),
)


def assunto_gatilho_prospeccao() -> str:
    return (getattr(settings, "CRM_GMAIL_ASSUNTO_GATILHO", "") or "").strip()


def assunto_bate_gatilho(assunto: str) -> bool:
    esperado = assunto_gatilho_prospeccao().casefold()
    recebido = (assunto or "").strip().casefold()
    return bool(esperado) and recebido == esperado


def _extrair_empresa_do_corpo(corpo: str) -> str:
    texto = (corpo or "").replace("\r\n", "\n")
    for pattern in _EMPRESA_BODY_PATTERNS:
        m = pattern.search(texto)
        if m:
            nome = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:")
            if len(nome) >= 2:
                return nome[:200]
    return ""


def _parse_nome_pessoa(nome: str, email: str) -> tuple[str, str]:
    nome = (nome or "").strip()
    if nome:
        partes = nome.split()
        if len(partes) == 1:
            return partes[0][:100], ""
        return partes[0][:100], " ".join(partes[1:])[:100]
    local = (email or "").split("@")[0].replace(".", " ").replace("_", " ").strip()
    if not local:
        return "Contato", ""
    partes = local.split()
    return (partes[0][:100].title(), " ".join(partes[1:])[:100].title() if len(partes) > 1 else "")


def _empresa_por_dominio(email: str) -> str:
    dominio = (email or "").split("@")[-1].strip().lower()
    if not dominio or dominio in {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com"}:
        return ""
    base = dominio.split(".")[0]
    if base in {"mail", "email", "smtp"}:
        return ""
    return base.replace("-", " ").title()[:200]


def criar_prospeccao_from_email(payload: dict) -> dict:
    """
    Cria card em Pré-vendas (Captura) a partir de e-mail enviado no Workspace.

    Retorno: {ok, created, oportunidade_id, funil_id, empresa, mensagem}
    """
    assunto = (payload.get("subject") or payload.get("assunto") or "").strip()
    if not assunto_bate_gatilho(assunto):
        return {
            "ok": False,
            "created": False,
            "skipped": True,
            "mensagem": (
                f"Assunto fora do gatilho. Esperado: “{assunto_gatilho_prospeccao()}”."
            ),
        }

    message_id = (payload.get("message_id") or payload.get("messageId") or "").strip()
    corpo = (payload.get("body") or payload.get("corpo") or "").strip()
    from_email = (payload.get("from_email") or payload.get("from") or "").strip().lower()
    from_name = (payload.get("from_name") or "").strip()

    destinatarios = payload.get("to") or payload.get("destinatarios") or []
    if isinstance(destinatarios, str):
        destinatarios = [{"email": destinatarios}]

    cliente_nome = (
        getattr(settings, "CRM_PROSPECCAO_CLIENTE_RSC", "RSC") or "RSC"
    ).strip()
    cliente = (
        ItemLista.objects.filter(
            tipo=TipoLista.CLIENTES_RSC, ativo=True, nome__iexact=cliente_nome
        ).first()
        or ItemLista.objects.filter(tipo=TipoLista.CLIENTES_RSC, ativo=True)
        .order_by("ordem", "nome")
        .first()
    )
    if cliente is None:
        return {
            "ok": False,
            "created": False,
            "mensagem": "Nenhum Cliente RSC cadastrado nas listas.",
        }

    funis = garantir_funis_para_cliente(cliente)
    funil = next((f for f in funis if f.tipo == TipoSubfunil.PRE_VENDAS), None)
    if funil is None:
        return {
            "ok": False,
            "created": False,
            "mensagem": f"Funil de pré-vendas não encontrado para {cliente.nome}.",
        }

    if message_id:
        marker = f"[gmail:{message_id}]"
        existente = (
            Oportunidade.objects.filter(funil=funil, observacoes__contains=marker)
            .order_by("-pk")
            .first()
        )
        if existente:
            return {
                "ok": True,
                "created": False,
                "oportunidade_id": existente.pk,
                "funil_id": funil.pk,
                "empresa": existente.empresa.nome,
                "mensagem": "Card já existia para este e-mail (idempotente).",
            }

    nome_empresa = (payload.get("empresa") or payload.get("company") or "").strip()
    if not nome_empresa:
        nome_empresa = _extrair_empresa_do_corpo(corpo)
    if not nome_empresa and destinatarios:
        primeiro = destinatarios[0] if isinstance(destinatarios[0], dict) else {}
        nome_empresa = _empresa_por_dominio(
            (primeiro.get("email") or str(destinatarios[0])).strip()
        )
    if not nome_empresa:
        nome_empresa = "Prospecção CAPEX"

    empresa = Empresa.objects.filter(nome__iexact=nome_empresa, ativa=True).first()
    if empresa is None:
        empresa = Empresa.objects.create(nome=nome_empresa[:200])
    if not empresa.clientes_rsc.filter(pk=cliente.pk).exists():
        empresa.clientes_rsc.add(cliente)

    contato = None
    if destinatarios:
        dest = destinatarios[0] if isinstance(destinatarios[0], dict) else {"email": destinatarios[0]}
        email_contato = (dest.get("email") or "").strip().lower()
        if email_contato:
            contato = Contato.objects.filter(
                empresa=empresa, email__iexact=email_contato, ativo=True
            ).first()
            if contato is None:
                nome_c, sobrenome_c = _parse_nome_pessoa(
                    dest.get("name") or dest.get("nome") or "", email_contato
                )
                contato = Contato.objects.create(
                    empresa=empresa,
                    nome=nome_c,
                    sobrenome=sobrenome_c,
                    email=email_contato,
                )
                contato.clientes_rsc.add(cliente)

    responsavel = None
    if from_email:
        responsavel = (
            Funcionario.objects.filter(ativo=True, usuario__email__iexact=from_email)
            .select_related("usuario")
            .first()
        )

    etapa = (
        funil.etapas.filter(nome="Captura").first()
        or funil.etapas.order_by("ordem", "pk").first()
    )

    marker_line = f"[gmail:{message_id}]" if message_id else ""
    to_resumo = []
    for d in destinatarios[:8]:
        if isinstance(d, dict):
            to_resumo.append(d.get("email") or d.get("name") or "")
        else:
            to_resumo.append(str(d))
    obs_parts = [
        marker_line,
        f"Assunto: {assunto}",
        f"De: {from_name or from_email}",
        f"Para: {', '.join(x for x in to_resumo if x)}",
        "",
        corpo[:4000],
    ]
    observacoes = "\n".join(p for p in obs_parts if p is not None).strip()

    opp = Oportunidade.objects.create(
        funil=funil,
        etapa=etapa,
        empresa=empresa,
        contato=contato,
        titulo=assunto[:200],
        responsavel=responsavel,
        origem=OrigemLead.EMAIL,
        formas_contato=[FormaContato.EMAIL],
        observacoes=observacoes,
        etapa_desde=timezone.now(),
        contato_email=(contato.email if contato else ""),
        contato_nome=(contato.nome_completo if contato else ""),
    )
    registrar_historico(
        opp,
        tipo=TipoHistoricoOpp.CRIADO,
        descricao=(
            "Card criado automaticamente a partir de e-mail Workspace "
            f"(assunto gatilho “{assunto_gatilho_prospeccao()}”)."
        ),
        autor=responsavel,
        etapa_para=etapa,
    )
    if corpo:
        registrar_historico(
            opp,
            tipo=TipoHistoricoOpp.NOTA,
            descricao=corpo[:2000],
            autor=responsavel,
        )

    return {
        "ok": True,
        "created": True,
        "oportunidade_id": opp.pk,
        "funil_id": funil.pk,
        "empresa": empresa.nome,
        "mensagem": "Card criado em RSC · Pré-vendas (Captura).",
    }
