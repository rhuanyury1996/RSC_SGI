"""Gera a proposta RAVEN (HTML A4 paginado) a partir do modelo, com os valores já preenchidos.

O modelo é a mesma página da proposta interativa. Aqui ele recebe um "preset":
a etapa de configuração some, os valores ficam travados e o cliente pode imprimir
ou salvar em PDF pelo navegador.
"""

from __future__ import annotations

import json
from pathlib import Path

from .calculo import INDUSTRIA, ResultadoRaven

MODELO = Path(__file__).resolve().parents[1] / "modelos_html" / "proposta_raven.html"
GANCHO = "window.__RAVEN_PRESET=null;"
NUMERO_MODELO = "26111301SW001"


def _br(valor) -> str:
    if valor is None:
        return ""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def preset(res: ResultadoRaven, *, cliente: str, contato: str, cidade: str, data) -> dict:
    """Configuração no formato que o script da proposta entende."""
    return {
        "cliente": cliente,
        "contato": contato,
        "cidade": cidade,
        "tipo": "ind" if res.tipo == INDUSTRIA else "cons",
        "plano": res.plano.chave,
        "planoNome": res.plano.nome,
        "usuarios": res.plano.usuarios,
        "vig": str(res.vigencia_meses),
        "lic": _br(res.valor_licenca),
        "impl": res.implantacao,
        "implv": _br(res.valor_implantacao),
        "visita": str(res.horas_visita or ""),
        "mig": bool(res.horas_pacote),
        "horas": str(res.horas_pacote or 40),
        "pag": res.pagamento,
        "val": str(res.validade_dias),
        "data": data.isoformat(),
    }


def gerar_html(numero: str, dados_preset: dict, modelo: Path = MODELO) -> bytes:
    texto = modelo.read_text(encoding="utf-8")
    if GANCHO not in texto:
        raise ValueError("Modelo da proposta RAVEN sem o gancho de preset.")
    js = json.dumps(dados_preset, ensure_ascii=False).replace("</", "<\\/")
    texto = texto.replace(GANCHO, f"window.__RAVEN_PRESET={js};", 1)
    texto = texto.replace(NUMERO_MODELO, numero)
    return texto.encode("utf-8")
