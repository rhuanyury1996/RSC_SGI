"""Importação de empresas e contatos a partir de planilhas Excel."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import transaction

from funcionarios.models import Funcionario

from .choices import ESTADOS_BR
from .models import (
    ClassificacaoUnidade,
    Contato,
    Empresa,
    ItemLista,
    TipoLista,
)


class ImportacaoErro(Exception):
    """Erro de validação/leitura da planilha."""


@dataclass
class ResultadoImportacao:
    empresas_criadas: int = 0
    empresas_atualizadas: int = 0
    contatos_criados: int = 0
    contatos_atualizados: int = 0
    contatos_sem_empresa: int = 0
    avisos: list[str] = field(default_factory=list)

    def mensagem(self) -> str:
        return (
            f"Empresas: {self.empresas_criadas} criadas, "
            f"{self.empresas_atualizadas} atualizadas. "
            f"Contatos: {self.contatos_criados} criados, "
            f"{self.contatos_atualizados} atualizados. "
            f"Sem empresa: {self.contatos_sem_empresa}."
        )


def _norm(texto) -> str:
    if texto is None:
        return ""
    s = str(texto).strip()
    return re.sub(r"\s+", " ", s)


def _fold(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def _header_map(headers: tuple) -> dict[str, int]:
    mapa = {}
    for i, h in enumerate(headers or ()):
        key = _fold(_norm(h))
        if key:
            mapa[key] = i
    return mapa


def _cell(row, mapa: dict[str, int], *aliases: str):
    for alias in aliases:
        idx = mapa.get(_fold(alias))
        if idx is not None and idx < len(row):
            return row[idx]
    return None


def _estado_uf(valor) -> str:
    raw = _norm(valor)
    if not raw:
        return ""
    if len(raw) == 2 and raw.upper() in dict(ESTADOS_BR):
        return raw.upper()
    por_nome = {_fold(nome): uf for uf, nome in ESTADOS_BR}
    return por_nome.get(_fold(raw), "")


def _classificacao(valor) -> str:
    raw = _fold(_norm(valor))
    if not raw:
        return ""
    mapa = {
        "filial": ClassificacaoUnidade.FILIAL,
        "matriz": ClassificacaoUnidade.MATRIZ,
        "sede corporativa": ClassificacaoUnidade.SEDE_CORPORATIVA,
        "sede": ClassificacaoUnidade.SEDE_CORPORATIVA,
    }
    return mapa.get(raw, "")


def _site_valido(valor) -> str:
    raw = _norm(valor)
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        URLValidator()(raw)
        return raw[:200]
    except ValidationError:
        return ""


def _email_valido(valor) -> str:
    raw = _norm(valor)
    if not raw:
        return ""
    try:
        validate_email(raw)
        return raw
    except ValidationError:
        return ""


def _telefone(valor) -> str:
    return _norm(valor)[:30]


def _obter_nicho(nome: str, cache: dict[str, ItemLista]) -> ItemLista | None:
    nome = _norm(nome)
    if not nome:
        return None
    key = _fold(nome)
    if key in cache:
        return cache[key]
    item, _ = ItemLista.objects.get_or_create(
        tipo=TipoLista.NICHO_MERCADOLOGICO,
        nome=nome[:150],
        defaults={"ativo": True, "ordem": 0},
    )
    cache[key] = item
    return item


def _obter_responsavel(
    nome: str, cache: dict[str, Funcionario | None]
) -> Funcionario | None:
    nome = _norm(nome)
    if not nome:
        return None
    key = _fold(nome)
    if key in cache:
        return cache[key]
    found = None
    for f in Funcionario.objects.filter(ativo=True):
        if _fold(f.nome_completo) == key or _fold(f.nome) == key:
            found = f
            break
    cache[key] = found
    return found


def ler_planilha(fonte: Path | str | BinaryIO) -> list[tuple]:
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportacaoErro(
            "Pacote openpyxl não instalado. Rode: pip install openpyxl"
        ) from exc

    if isinstance(fonte, (str, Path)):
        path = Path(fonte)
        if not path.exists():
            raise ImportacaoErro(f"Arquivo não encontrado: {path}")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    else:
        # UploadedFile / BytesIO
        if hasattr(fonte, "seek"):
            try:
                fonte.seek(0)
            except Exception:
                pass
        wb = openpyxl.load_workbook(fonte, read_only=True, data_only=True)

    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    return rows or []


@transaction.atomic
def importar_empresas_contatos(
    empresas_fonte: Path | str | BinaryIO,
    contatos_fonte: Path | str | BinaryIO,
    *,
    dry_run: bool = False,
) -> ResultadoImportacao:
    emp_rows = ler_planilha(empresas_fonte)
    con_rows = ler_planilha(contatos_fonte)
    if len(emp_rows) < 2:
        raise ImportacaoErro("Planilha de empresas sem dados.")
    if len(con_rows) < 2:
        raise ImportacaoErro("Planilha de contatos sem dados.")

    emp_map = _header_map(emp_rows[0])
    con_map = _header_map(con_rows[0])
    resultado = ResultadoImportacao()

    nicho_cache: dict[str, ItemLista] = {
        _fold(i.nome): i
        for i in ItemLista.objects.filter(tipo=TipoLista.NICHO_MERCADOLOGICO)
    }
    resp_cache: dict[str, Funcionario | None] = {}
    empresas_por_nome: dict[str, Empresa] = {
        _fold(e.nome): e for e in Empresa.objects.all()
    }

    for row in emp_rows[1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        nome = _norm(_cell(row, emp_map, "Nome da Empresa", "Título", "Titulo"))
        if not nome:
            continue
        site = _site_valido(_cell(row, emp_map, "Site da empresa"))
        nicho = _obter_nicho(
            _norm(_cell(row, emp_map, "Nicho mercadológico", "Nicho mercadologico")),
            nicho_cache,
        )
        classif = _classificacao(
            _cell(row, emp_map, "Classificação da unidade", "Classificacao da unidade")
        )
        tel1 = _telefone(_cell(row, emp_map, "Telefone (Portaria)"))
        tel2 = _telefone(_cell(row, emp_map, "Telefone 2 (Portaria)"))
        email = _email_valido(_cell(row, emp_map, "E-mail geral", "Email geral"))
        cidade = _norm(_cell(row, emp_map, "Cidade"))[:120]
        estado = _estado_uf(_cell(row, emp_map, "Estado"))
        codigo = _norm(_cell(row, emp_map, "Código", "Codigo"))
        status = _fold(_norm(_cell(row, emp_map, "Status")))
        ativa = status in ("", "ativo", "ativa", "active")

        obs_parts = []
        if codigo:
            obs_parts.append(f"Código externo: {codigo}")
        observacoes = "\n".join(obs_parts)

        key = _fold(nome)
        existente = empresas_por_nome.get(key)
        campos = {
            "site": site,
            "nicho": nicho,
            "classificacao_unidade": classif,
            "telefone_portaria": tel1,
            "telefone_portaria_2": tel2,
            "email_geral": email,
            "cidade": cidade,
            "estado": estado,
            "ativa": ativa,
        }
        if observacoes:
            campos["observacoes"] = observacoes

        if existente:
            for k, v in campos.items():
                setattr(existente, k, v)
            if not dry_run:
                existente.save()
            resultado.empresas_atualizadas += 1
            empresas_por_nome[key] = existente
        else:
            emp = Empresa(nome=nome[:200], **campos)
            if not dry_run:
                emp.save()
            empresas_por_nome[key] = emp
            resultado.empresas_criadas += 1

    for row in con_rows[1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        nome = _norm(_cell(row, con_map, "Nome"))
        if not nome:
            continue
        sobrenome = _norm(_cell(row, con_map, "Sobrenome"))[:100]
        email = _email_valido(_cell(row, con_map, "E-mail", "Email"))
        ramal = _telefone(_cell(row, con_map, "Telefone (Ramal)"))
        whats = _telefone(
            _cell(
                row,
                con_map,
                "Telefone (WhatsApp)",
                "Telefone (WhatAppp)",
                "Telefone (WhatApp)",
            )
        )
        empresa_nome = _norm(_cell(row, con_map, "Empresa"))
        responsavel = _obter_responsavel(
            _norm(
                _cell(
                    row,
                    con_map,
                    "Responsável pelo contato",
                    "Responsavel pelo contato",
                )
            ),
            resp_cache,
        )
        status = _fold(_norm(_cell(row, con_map, "Status")))
        ativo = status in ("", "ativo", "ativa", "active")

        empresa = empresas_por_nome.get(_fold(empresa_nome)) if empresa_nome else None
        if empresa is None:
            resultado.contatos_sem_empresa += 1
            resultado.avisos.append(
                f"Contato sem empresa: {nome} {sobrenome} -> '{empresa_nome}'"
            )
            continue

        campos = {
            "email": email,
            "telefone_ramal": ramal,
            "telefone_whatsapp": whats,
            "responsavel": responsavel,
            "ativo": ativo,
        }

        if dry_run or not getattr(empresa, "pk", None):
            resultado.contatos_criados += 1
            continue

        qs = Contato.objects.filter(empresa=empresa, nome__iexact=nome)
        if sobrenome:
            qs = qs.filter(sobrenome__iexact=sobrenome)
        else:
            qs = qs.filter(sobrenome="")
        existente = qs.first()
        if existente:
            for k, v in campos.items():
                setattr(existente, k, v)
            existente.save()
            resultado.contatos_atualizados += 1
        else:
            Contato.objects.create(
                empresa=empresa,
                nome=nome[:100],
                sobrenome=sobrenome,
                **campos,
            )
            resultado.contatos_criados += 1

    if dry_run:
        transaction.set_rollback(True)

    return resultado
