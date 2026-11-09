"""Monta o orçamento (preços, número, avisos) e gera o docx em memória."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Callable

from .gerador_docx import gerar_docx
from .modelos import Cliente, Orcamento, PedidoOrcamento, TipoCliente
from .numeracao import nome_arquivo, numero_proposta
from .parametros import Parametros
from .precos import linhas_software, linhas_treinamento

MODELO_DOCX = Path(__file__).resolve().parent.parent / "modelos_docx" / "modelo_orcamento_gexcon.docx"


def somar_meses(d: date, meses: int) -> date:
    ano, mes = divmod(d.month - 1 + meses, 12)
    ano, mes = d.year + ano, mes + 1
    bissexto = ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)
    dias = [31, 29 if bissexto else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    return date(ano, mes, min(d.day, dias))


def resolver_periodos(pedido: PedidoOrcamento, params: Parametros) -> list[int]:
    if not pedido.periodos_meses:
        return list(params.periodos_meses)
    periodos = sorted(set(pedido.periodos_meses))
    invalidos = [m for m in periodos if m not in params.periodos_disponiveis]
    if invalidos:
        raise ValueError(f"Período(s) não disponível(is): {invalidos}. Opções: {params.periodos_disponiveis}")
    if len(periodos) > params.max_periodos_por_proposta:
        raise ValueError(
            f"Escolha até {params.max_periodos_por_proposta} períodos por proposta "
            "(é o número de colunas da tabela de preços)."
        )
    return periodos


AVISOS_CATEGORIA = {
    "academica": [
        "Licença acadêmica (Termos Gexcon 3.2): só para instituição de ensino reconhecida, "
        "com aprovação da Gexcon; uso restrito a funcionários e alunos matriculados, para "
        "ensino, aprendizado e pesquisa sem fins lucrativos.",
        "Licença acadêmica não pode ser usada para consultoria, benchmarking ou fins internos "
        "da instituição; publicações devem citar o produto e a versão; suporte a critério da Gexcon.",
    ],
    "orgao_publico": [
        "Licença para órgão público: confirme com a Gexcon a elegibilidade do cliente ao desconto.",
    ],
}


def resolver_tipo_cliente(pedido: PedidoOrcamento, data: date, params: Parametros) -> tuple[TipoCliente, list[str]]:
    """Renovação vale até `prazo_renovacao_meses` após o vencimento; depois, preço de cliente novo."""
    if pedido.tipo_cliente is not TipoCliente.RENOVACAO:
        return TipoCliente.NOVO, []
    if pedido.vencimento_licenca is None:
        return TipoCliente.RENOVACAO, ["Renovação sem data de vencimento informada: prazo não verificado."]
    limite = somar_meses(pedido.vencimento_licenca, params.prazo_renovacao_meses)
    if data > limite:
        return TipoCliente.NOVO, [
            f"Licença vencida em {pedido.vencimento_licenca:%d/%m/%Y}; prazo de renovação até "
            f"{limite:%d/%m/%Y}. Aplicado preço de cliente novo."
        ]
    return TipoCliente.RENOVACAO, []


def montar_orcamento(
    pedido: PedidoOrcamento,
    params: Parametros,
    cliente: Cliente,
    proximo_sequencial: Callable[[date], int],
) -> Orcamento:
    data = pedido.data or date.today()
    if data > params.validade_ate:
        raise ValueError(
            f"Data da proposta ({data:%d/%m/%Y}) após a validade da tabela "
            f"({params.validade_ate:%d/%m/%Y}). Atualize os parâmetros."
        )
    periodos = resolver_periodos(pedido, params)
    tipo, avisos = resolver_tipo_cliente(pedido, data, params)
    reajuste = params.reajuste_lista[tipo.value]
    desconto = params.desconto(pedido.categoria_licenca)
    avisos = avisos + AVISOS_CATEGORIA.get(pedido.categoria_licenca, [])
    seq = pedido.sequencial or proximo_sequencial(data)
    numero = numero_proposta(data, seq)
    return Orcamento(
        numero=numero,
        data=data,
        validade=params.validade_ate,
        nome_arquivo=nome_arquivo(numero, cliente.nome_curto, pedido.escopo),
        cliente=cliente,
        contato=cliente.contato(pedido.contato_id),
        escopo=pedido.escopo,
        periodos_meses=periodos,
        linhas_software=linhas_software(
            pedido.escopo,
            pedido.incluir_usuario_adicional,
            params,
            periodos,
            reajuste,
            desconto=desconto,
            unidades=pedido.unidades,
            dongles=pedido.dongles,
        ),
        linhas_treinamento=linhas_treinamento(pedido.treinamentos, params),
        tipo_cliente=tipo,
        avisos=tuple(avisos),
        categoria_licenca=pedido.categoria_licenca,
        nome_categoria=params.nome_categoria(pedido.categoria_licenca),
        desconto=desconto,
        unidades=pedido.unidades,
    )


def gerar_bytes(orc: Orcamento, params: Parametros, modelo: str | Path = MODELO_DOCX) -> bytes:
    buffer = io.BytesIO()
    gerar_docx(orc, params, modelo, buffer)
    return buffer.getvalue()
