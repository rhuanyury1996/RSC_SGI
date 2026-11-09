"""Preenche o modelo docx da proposta, preservando a formatação original.

Trabalha diretamente no XML das tabelas do modelo (Orc_AAMMDD-1_Empresa_E&R).
Antes de alterar, valida os rótulos esperados: se o modelo mudar de layout,
o gerador falha com uma mensagem clara em vez de gerar um documento errado.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from .modelos import PRODUTO_ER, Escopo, Orcamento
from .parametros import Parametros
from .precos import formatar_euro, rotulo_periodo

# Índices das tabelas no modelo
T_CABECALHO, T_RESUMO_PROD, T_PRECO_ANUAL, T_PRECOS = 0, 1, 2, 3
T_RESUMO_SERV, T_TREINAMENTO, T_NUM_PAG2, T_TOTAIS, T_ASSINATURA = 4, 5, 6, 7, 8

ROTULOS_ESPERADOS = {
    (T_CABECALHO, 0, 1): "N° da Proposta",
    (T_RESUMO_PROD, 0, 0): "Resumo dos Produtos",
    (T_PRECOS, 0, 0): "Item",
    (T_RESUMO_SERV, 0, 0): "Resumo dos Serviços",
    (T_TREINAMENTO, 0, 0): "Treinamento",
    (T_NUM_PAG2, 0, 1): "N° da Proposta",
    (T_TOTAIS, 1, 0): "SERVIÇOS",
}


class ModeloIncompativel(RuntimeError):
    pass


# --------------------------------------------------------------------------- helpers XML


def _tc(tabela, linha: int, col: int):
    return tabela._tbl.tr_lst[linha].tc_lst[col]


def _texto(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def _definir_texto(tc, linhas: str | list[str]) -> None:
    """Substitui o texto da célula mantendo a formatação do primeiro run."""
    if isinstance(linhas, str):
        linhas = [linhas]
    paragrafos = tc.findall(qn("w:p"))
    modelo = paragrafos[0]
    runs = [r for r in modelo.iter(qn("w:r")) if r.find(qn("w:t")) is not None]
    for r in runs[1:]:
        r.getparent().remove(r)
    for pe in modelo.findall(qn("w:proofErr")):
        modelo.remove(pe)
    if runs:
        # O run pode ter vários w:t separados por w:br (ex.: assinatura): fica só o primeiro
        t = runs[0].find(qn("w:t"))
        for filho in list(runs[0]):
            if filho is not t and filho.tag != qn("w:rPr"):
                runs[0].remove(filho)
    else:  # célula vazia: cria um run
        r = modelo.makeelement(qn("w:r"), {})
        modelo.append(r)
        t = r.makeelement(qn("w:t"), {})
        r.append(t)
    t.text = linhas[0] if linhas else ""
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for p in paragrafos[1:]:
        tc.remove(p)
    anterior = modelo
    for texto in linhas[1:]:
        novo = copy.deepcopy(modelo)
        novo.find(".//" + qn("w:t")).text = texto
        anterior.addnext(novo)
        anterior = novo


def _remover(el) -> None:
    el.getparent().remove(el)


def _remover_com_paragrafo_vazio(el) -> None:
    """Remove o elemento e o parágrafo vazio logo após (espaçamento)."""
    seguinte = el.getnext()
    _remover(el)
    if seguinte is not None and seguinte.tag == qn("w:p") and not _texto(seguinte).strip():
        _remover(seguinte)


def _remover_coluna(tabela, col: int) -> None:
    """Remove a coluna e redistribui a largura entre as colunas de valores."""
    grid = tabela._tbl.tblGrid
    cols = grid.findall(qn("w:gridCol"))
    largura = int(cols[col].get(qn("w:w")))
    _remover(cols[col])
    for tr in tabela._tbl.tr_lst:
        _remover(tr.tc_lst[col])
    restantes = grid.findall(qn("w:gridCol"))[1:]  # coluna 0 é o "Item"
    if restantes:
        extra = largura // len(restantes)
        for c in restantes:
            c.set(qn("w:w"), str(int(c.get(qn("w:w"))) + extra))


def _rotulo_periodo(meses: int) -> str:
    # O modelo usa "12 meses" para 1 ano; acima disso, "2 anos", "3 anos"...
    return f"{meses} meses" if meses == 12 else rotulo_periodo(meses)


def _validar_modelo(doc) -> None:
    if len(doc.tables) != 9:
        raise ModeloIncompativel(f"Esperadas 9 tabelas no modelo, encontradas {len(doc.tables)}")
    for (t, l, c), rotulo in ROTULOS_ESPERADOS.items():
        texto = _texto(_tc(doc.tables[t], l, c))
        if rotulo not in texto:
            raise ModeloIncompativel(f"Tabela {t} ({l},{c}): esperado '{rotulo}', encontrado '{texto}'")


# --------------------------------------------------------------------------- gerador


def gerar_docx(orc: Orcamento, params: Parametros, modelo: str | Path, destino: str | Path) -> Path:
    doc = Document(str(modelo))
    _validar_modelo(doc)
    t = doc.tables
    cli = orc.cliente
    dpr = params.responsavel(orc.escopo)
    assinatura = params.assinatura
    data_txt = f"{orc.data:%d/%m/%Y}"
    validade_txt = f"{orc.validade:%d/%m/%Y}"

    # Cabeçalho: cliente, número, datas, contatos
    cab = t[T_CABECALHO]
    _definir_texto(_tc(cab, 0, 0), [cli.razao_social, f"CNPJ. {cli.cnpj}", *cli.endereco_linhas])
    _definir_texto(_tc(cab, 0, 2), orc.numero)
    _definir_texto(_tc(cab, 1, 2), data_txt)
    _definir_texto(_tc(cab, 2, 2), validade_txt)
    contato = orc.contato
    _definir_texto(_tc(cab, 4, 0), f"Pessoa de contato: {contato.nome}")
    _definir_texto(_tc(cab, 5, 1), contato.fone)
    _definir_texto(_tc(cab, 5, 3), dpr.nome)
    _definir_texto(_tc(cab, 6, 1), contato.email)
    _definir_texto(_tc(cab, 6, 3), dpr.fone)
    _definir_texto(_tc(cab, 7, 2), dpr.fax)
    _definir_texto(_tc(cab, 8, 2), dpr.email)

    # Resumo dos produtos
    resumo = "EFFECTS e RISKCURVES" if orc.escopo is Escopo.EFFECTS_RISKCURVES else "EFFECTS"
    if orc.categoria_licenca != "comercial":
        resumo = f"{resumo} – licença {orc.nome_categoria.lower()}"
    _definir_texto(_tc(t[T_RESUMO_PROD], 0, 1), resumo)

    # Tabela de preços por período
    tp = t[T_PRECOS]
    n_periodos = len(orc.periodos_meses)
    n_cols_valor = len(tp._tbl.tr_lst[0].tc_lst) - 1
    if n_periodos > n_cols_valor:
        raise ModeloIncompativel(f"O modelo comporta até {n_cols_valor} períodos")
    for _ in range(n_cols_valor - n_periodos):
        _remover_coluna(tp, n_cols_valor)  # sempre a última
        n_cols_valor -= 1
    for i, meses in enumerate(orc.periodos_meses, start=1):
        _definir_texto(_tc(tp, 0, i), _rotulo_periodo(meses))

    linhas_modelo = list(tp._tbl.tr_lst[1:])  # EFFECTS, E+R, adicional
    por_descricao = {_texto(tr.tc_lst[0]).strip(): tr for tr in linhas_modelo}
    usadas = set()
    ancora = None  # última linha preenchida (itens extras entram logo depois)
    for linha in orc.linhas_software:
        tr = por_descricao.get(linha.descricao)
        if tr is None:
            raise ModeloIncompativel(f"Linha '{linha.descricao}' não existe no modelo")
        if id(tr) in usadas:  # item extra (ex.: Dongle): copia a formatação da linha
            tr = copy.deepcopy(tr)
            ancora.addnext(tr)
        usadas.add(id(tr))
        ancora = tr
        if linha.texto != linha.descricao:
            _definir_texto(tr.tc_lst[0], linha.texto)
        for i, meses in enumerate(orc.periodos_meses, start=1):
            _definir_texto(tr.tc_lst[i], formatar_euro(linha.precos_por_periodo[meses]))
    for tr in linhas_modelo:
        if id(tr) not in usadas:
            _remover(tr)

    # Tabela "1 ano" isolada fica redundante com a coluna de 12 meses
    _remover_com_paragrafo_vazio(t[T_PRECO_ANUAL]._tbl)

    # Treinamentos
    body = doc.element.body
    if orc.linhas_treinamento:
        descricao_serv = ",  ".join(
            f"{l.produto} – {l.tipo.lower()}" for l in orc.linhas_treinamento
        )
        _definir_texto(_tc(t[T_RESUMO_SERV], 0, 1), f"Treinamentos de {descricao_serv}")

        tt = t[T_TREINAMENTO]
        tr_effects, tr_er, tr_total = tt._tbl.tr_lst[1], tt._tbl.tr_lst[2], tt._tbl.tr_lst[3]
        modelo_por_produto = {"EFFECTS": tr_effects, PRODUTO_ER: tr_er}
        novas = []
        for l in orc.linhas_treinamento:
            tr = copy.deepcopy(modelo_por_produto[l.produto])
            c = tr.tc_lst
            _definir_texto(c[0], l.produto)
            _definir_texto(c[1], l.tipo)
            _definir_texto(c[2], f"{l.horas} horas")
            _definir_texto(c[3], str(l.alunos))
            _definir_texto(c[4], formatar_euro(l.preco_unitario))
            novas.append(tr)
        for tr in novas:
            tr_total.addprevious(tr)
        _remover(tr_effects)
        _remover(tr_er)
        _definir_texto(tr_total.tc_lst[1], formatar_euro(orc.total_treinamentos))
        tem_online = any(l.tipo.lower() == "online" for l in orc.linhas_treinamento)
    else:
        _remover_com_paragrafo_vazio(t[T_RESUMO_SERV]._tbl)
        _remover_com_paragrafo_vazio(t[T_TREINAMENTO]._tbl)
        tem_online = False

    # Totais: SOFTWARE mantém o texto do modelo; SERVIÇOS = módulo 12 meses + treinamentos
    _definir_texto(_tc(t[T_TOTAIS], 1, 1), formatar_euro(orc.total_servicos))

    if not tem_online:
        for p in body.iter(qn("w:p")):
            if _texto(p).strip().startswith("Treinamento online via"):
                _remover(p)
                break

    # Página 2: número e validade
    _definir_texto(_tc(t[T_NUM_PAG2], 0, 2), orc.numero)
    _definir_texto(_tc(t[T_NUM_PAG2], 1, 2), validade_txt)

    # Assinaturas
    ass = t[T_ASSINATURA]
    _definir_texto(_tc(ass, 2, 1), [assinatura.nome, assinatura.empresa])
    _definir_texto(_tc(ass, 2, 3), f"Cliente: {cli.razao_social}")

    # Rodapé (caixas de texto): data e número
    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/footer") or rel.reltype.endswith("/header"):
            for wt in rel.target_part.element.iter(qn("w:t")):
                if wt.text:
                    wt.text = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", data_txt, wt.text)
                    wt.text = re.sub(r"(Proposta:\s*)\d{6}-\d+", rf"\g<1>{orc.numero}", wt.text)

    if hasattr(destino, "write"):  # arquivo em memória (SGI grava no banco)
        doc.save(destino)
        return destino
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destino))
    return destino
