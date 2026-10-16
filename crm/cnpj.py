"""Consulta pública de CNPJ via BrasilAPI (dados da Receita Federal)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any


BRASILAPI_CNPJ = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


class CnpjErro(Exception):
    """Falha na consulta ou CNPJ inválido."""


def somente_digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def formatar_cnpj(cnpj: str) -> str:
    d = somente_digitos(cnpj)[:14]
    if len(d) != 14:
        return cnpj or ""
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def cnpj_valido(cnpj: str) -> bool:
    d = somente_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False

    def _digito(base: str, pesos: list[int]) -> str:
        soma = sum(int(n) * p for n, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = _digito(d[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = _digito(d[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return d[-2:] == d1 + d2


def formatar_telefone_br(raw: str) -> str:
    dig = re.sub(r"\D", "", raw or "")
    if dig.startswith("55") and len(dig) > 11:
        dig = dig[2:]
    dig = dig[:11]
    if len(dig) == 11:
        return f"({dig[:2]}) {dig[2:7]}-{dig[7:]}"
    if len(dig) == 10:
        return f"({dig[:2]}) {dig[2:6]}-{dig[6:]}"
    return dig


def _titulo(texto: str) -> str:
    texto = (texto or "").strip()
    if not texto:
        return ""
    # Municípios da RF vêm em maiúsculas
    return " ".join(p.capitalize() if len(p) > 2 else p.lower() for p in texto.split())


def consultar_cnpj(cnpj: str) -> dict[str, Any]:
    """
    Retorna dados normalizados para o formulário de empresa.
    Fonte: BrasilAPI (Receita Federal).
    """
    digitos = somente_digitos(cnpj)
    if len(digitos) != 14:
        raise CnpjErro("Informe um CNPJ com 14 dígitos.")
    if not cnpj_valido(digitos):
        raise CnpjErro("CNPJ inválido.")

    url = BRASILAPI_CNPJ.format(cnpj=digitos)
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "SGI-RSC/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise CnpjErro("CNPJ não encontrado na base pública.") from exc
        raise CnpjErro("Serviço de consulta indisponível no momento.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CnpjErro("Não foi possível consultar o CNPJ agora.") from exc

    fantasia = (payload.get("nome_fantasia") or "").strip()
    razao = (payload.get("razao_social") or "").strip()
    nome = fantasia or razao

    tel1 = formatar_telefone_br(str(payload.get("ddd_telefone_1") or ""))
    tel2 = formatar_telefone_br(str(payload.get("ddd_telefone_2") or ""))
    email = (payload.get("email") or "").strip().lower()
    cidade = _titulo(str(payload.get("municipio") or ""))
    uf = (payload.get("uf") or "").strip().upper()[:2]

    return {
        "cnpj": formatar_cnpj(digitos),
        "nome": nome,
        "razao_social": razao,
        "nome_fantasia": fantasia,
        "telefone_portaria": tel1,
        "telefone_portaria_2": tel2,
        "email_geral": email,
        "cidade": cidade,
        "estado": uf,
        "situacao": (payload.get("descricao_situacao_cadastral") or "").strip(),
    }
