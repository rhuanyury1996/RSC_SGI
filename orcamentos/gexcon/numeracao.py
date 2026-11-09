"""Número da proposta (AAMMDD-seq) e nome do arquivo."""

from __future__ import annotations

import re
from datetime import date

from .modelos import Escopo

_INVALIDOS = re.compile(r'[<>:"/\\|?*]+')


def numero_proposta(data: date, sequencial: int) -> str:
    if sequencial < 1:
        raise ValueError("Sequencial deve ser >= 1")
    return f"{data:%y%m%d}-{sequencial}"


def limpar_nome(nome: str) -> str:
    """Remove caracteres inválidos em nomes de arquivo do Windows."""
    return re.sub(r"\s+", " ", _INVALIDOS.sub("", nome)).strip()


def nome_arquivo(numero: str, nome_empresa: str, escopo: Escopo) -> str:
    return f"Orc_{numero}_{limpar_nome(nome_empresa)}_{escopo.value}.docx"
