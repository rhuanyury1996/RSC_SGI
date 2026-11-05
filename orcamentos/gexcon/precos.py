"""Motor de preços: lista Gexcon x (1 + fator Brasil) x fator de período."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .modelos import (
    PRODUTO_EFFECTS,
    PRODUTO_ER,
    Escopo,
    LinhaSoftware,
    LinhaTreinamento,
    PedidoTreinamento,
)
from .parametros import Parametros

CENTAVO = Decimal("0.01")
EURO = Decimal("1")


def _arredondar(valor: Decimal, inteiro: bool) -> Decimal:
    return valor.quantize(EURO if inteiro else CENTAVO, rounding=ROUND_HALF_UP).quantize(CENTAVO)


def preco_software(
    produto: str, meses: int, p: Parametros, adicional: bool = False, reajuste: Decimal = Decimal("0")
) -> Decimal:
    """lista Gexcon x (1 + reajuste do tipo de cliente) x (1 + fator Brasil) x fator do período"""
    if produto not in p.precos_lista:
        raise KeyError(f"Produto sem preço de lista: {produto}")
    valor = p.precos_lista[produto] * (1 + reajuste) * (1 + p.fator_brasil) * p.fatores_periodo[meses]
    if adicional:
        valor *= p.fator_usuario_adicional
    return _arredondar(valor, p.arredondar_software_euro_inteiro)


def linhas_software(
    escopo: Escopo,
    incluir_adicional: bool,
    p: Parametros,
    periodos: list[int] | None = None,
    reajuste: Decimal = Decimal("0"),
) -> list[LinhaSoftware]:
    periodos = periodos or p.periodos_meses

    def linha(desc: str, produto: str, adicional: bool = False) -> LinhaSoftware:
        return LinhaSoftware(
            descricao=desc,
            precos_por_periodo={m: preco_software(produto, m, p, adicional, reajuste) for m in periodos},
        )

    linhas = [linha(PRODUTO_EFFECTS, PRODUTO_EFFECTS)]
    if escopo is Escopo.EFFECTS_RISKCURVES:
        linhas.append(linha(PRODUTO_ER, PRODUTO_ER))
    if incluir_adicional:
        linhas.append(linha("EFFECTS (usuário adicional)", PRODUTO_EFFECTS, adicional=True))
    return linhas


def linhas_treinamento(pedidos: list[PedidoTreinamento], p: Parametros) -> list[LinhaTreinamento]:
    linhas = []
    for t in pedidos:
        cfg = p.treinamentos.get(t.produto)
        if cfg is None:
            raise KeyError(f"Treinamento sem parâmetros: {t.produto}")
        if t.tipo not in cfg["precos_lista"]:
            raise KeyError(f"Treinamento {t.produto} sem preço para o tipo '{t.tipo}'")
        if t.alunos < 1:
            raise ValueError("Quantidade de alunos deve ser >= 1")
        fator = (1 + p.fator_brasil) if cfg["aplicar_fator_brasil"] else Decimal("1")
        preco = _arredondar(cfg["precos_lista"][t.tipo] * fator, inteiro=False)
        linhas.append(LinhaTreinamento(t.produto, t.tipo, cfg["horas"], t.alunos, preco))
    return linhas


def formatar_euro(valor: Decimal) -> str:
    """Decimal('9450') -> '€ 9.450,00'"""
    texto = f"{valor.quantize(CENTAVO):,.2f}"
    return "€ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")
