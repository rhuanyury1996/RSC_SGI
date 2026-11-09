"""Motor de preços, igual ao Deal Builder do XSuite Price Builder 2026 (EUR, DPR).

Planilha: Ano 1 = lista/unidade x modificador da duração x unidades x (1 - desconto + fator Brasil)
          Anos 2 a 5 = ano anterior x (1 + fator multi-ano)
O desconto (órgão público 45%, acadêmica 90%) entra somado ao fator Brasil, como na planilha.
"""

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
ZERO = Decimal("0")


def _arredondar(valor: Decimal, inteiro: bool) -> Decimal:
    return valor.quantize(EURO if inteiro else CENTAVO, rounding=ROUND_HALF_UP).quantize(CENTAVO)


def fator_venda(p: Parametros, desconto: Decimal = ZERO) -> Decimal:
    """(1 - desconto + fator Brasil), como a coluna "Year 1" do Deal Builder."""
    return 1 - desconto + p.fator_brasil


def precos_anuais(
    produto: str,
    meses: int,
    p: Parametros,
    adicional: bool = False,
    reajuste: Decimal = ZERO,
    desconto: Decimal = ZERO,
    unidades: int = 1,
) -> list[Decimal]:
    """Preço de cada ano do período (um item só para períodos de até 12 meses)."""
    if produto not in p.precos_lista:
        raise KeyError(f"Produto sem preço de lista: {produto}")
    if unidades < 1:
        raise ValueError("Quantidade de licenças deve ser >= 1")
    base = p.precos_lista[produto] * (1 + reajuste) * unidades * fator_venda(p, desconto)
    if adicional:
        base *= p.fator_usuario_adicional
    if meses <= 12:
        if meses not in p.fatores_periodo:
            raise KeyError(f"Sem fator de período para {meses} meses")
        return [base * p.fatores_periodo[meses]]
    anos = meses // 12
    return [base * (1 + p.fator_multi_ano) ** k for k in range(anos)]


def preco_software(
    produto: str,
    meses: int,
    p: Parametros,
    adicional: bool = False,
    reajuste: Decimal = ZERO,
    desconto: Decimal = ZERO,
    unidades: int = 1,
) -> Decimal:
    """Total do período, arredondado ao euro inteiro (meio para cima) só no final."""
    total = sum(precos_anuais(produto, meses, p, adicional, reajuste, desconto, unidades), ZERO)
    return _arredondar(total, p.arredondar_software_euro_inteiro)


def _rotulo(nome: str, unidades: int) -> str:
    return nome if unidades == 1 else f"{nome} ({unidades} licenças)"


def linhas_software(
    escopo: Escopo,
    incluir_adicional: bool,
    p: Parametros,
    periodos: list[int] | None = None,
    reajuste: Decimal = ZERO,
    desconto: Decimal = ZERO,
    unidades: int = 1,
    dongles: int = 0,
) -> list[LinhaSoftware]:
    periodos = periodos or p.periodos_meses

    def linha(desc: str, produto: str, adicional: bool = False, qtd: int = unidades) -> LinhaSoftware:
        anual = {
            m: [
                _arredondar(v, p.arredondar_software_euro_inteiro)
                for v in precos_anuais(produto, m, p, adicional, reajuste, desconto, qtd)
            ]
            for m in periodos
            if m > 12
        }
        return LinhaSoftware(
            descricao=desc,
            precos_por_periodo={
                m: preco_software(produto, m, p, adicional, reajuste, desconto, qtd) for m in periodos
            },
            rotulo=_rotulo(desc, qtd) if not adicional else desc,
            anual=anual,
        )

    linhas = [linha(PRODUTO_EFFECTS, PRODUTO_EFFECTS)]
    if escopo is Escopo.EFFECTS_RISKCURVES:
        linhas.append(linha(PRODUTO_ER, PRODUTO_ER))
    if incluir_adicional:
        linhas.append(linha("EFFECTS (usuário adicional)", PRODUTO_EFFECTS, adicional=True, qtd=1))
    if dongles:
        preco = (p.itens_opcionais or {}).get("Dongle")
        if preco is None:
            raise KeyError("Dongle sem preço na tabela de parâmetros")
        # Item avulso: mesmo valor em todas as colunas, sem fator de período nem multi-ano.
        valor = _arredondar(preco * dongles * fator_venda(p, desconto), inteiro=False)
        linhas.append(
            LinhaSoftware(
                descricao=PRODUTO_EFFECTS,
                precos_por_periodo={m: valor for m in periodos},
                rotulo="Dongle (chave física)" if dongles == 1 else f"Dongle (chave física) x{dongles}",
            )
        )
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


def rotulo_periodo(meses: int) -> str:
    if meses >= 12 and meses % 12 == 0:
        anos = meses // 12
        return "1 ano" if anos == 1 else f"{anos} anos"
    return "1 mês" if meses == 1 else f"{meses} meses"
