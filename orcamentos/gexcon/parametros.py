"""Parâmetros de precificação, carregados de JSON (um arquivo por tabela/ano)."""

from __future__ import annotations

import json
from datetime import date
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


def _dec(valor: Any) -> Decimal:
    return Decimal(str(valor))


@dataclass(frozen=True)
class ResponsavelDPR:
    """Contato do quadro "Em caso de quaisquer questões..." (varia com o escopo)."""

    nome: str
    fone: str
    fax: str
    email: str


@dataclass(frozen=True)
class Assinatura:
    nome: str
    empresa: str


@dataclass(frozen=True)
class Parametros:
    versao_tabela: str
    fator_brasil: Decimal
    reajuste_lista: dict[str, Decimal]  # "novo" / "renovacao": % sobre a lista Gexcon do ano
    prazo_renovacao_meses: int  # após o vencimento, renovação vira preço de cliente novo
    validade_ate: date  # data fixa de validade das propostas da tabela vigente
    arredondar_software_euro_inteiro: bool
    precos_lista: dict[str, Decimal]
    fator_usuario_adicional: Decimal
    periodos_meses: list[int]
    fatores_periodo: dict[int, Decimal]
    treinamentos: dict[str, dict[str, Any]]
    responsaveis: dict[str, ResponsavelDPR]  # chave: valor do Escopo ("E&R" / "E")
    assinatura: Assinatura

    def responsavel(self, escopo) -> ResponsavelDPR:
        chave = getattr(escopo, "value", escopo)
        try:
            return self.responsaveis[chave]
        except KeyError:
            raise KeyError(f"Sem responsável DPR cadastrado para o escopo {chave}") from None

    @classmethod
    def carregar(cls, caminho: str | Path) -> "Parametros":
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return cls.de_dict(dados)

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Parametros":
        params = cls(
            versao_tabela=d["versao_tabela"],
            fator_brasil=_dec(d["fator_brasil"]),
            reajuste_lista={k: _dec(v) for k, v in d.get("reajuste_lista", {}).items()},
            prazo_renovacao_meses=int(d.get("prazo_renovacao_meses", 1)),
            validade_ate=date.fromisoformat(d["validade_ate"]),
            arredondar_software_euro_inteiro=bool(d["arredondar_software_euro_inteiro"]),
            precos_lista={k: _dec(v) for k, v in d["precos_lista"].items()},
            fator_usuario_adicional=_dec(d["fator_usuario_adicional"]),
            periodos_meses=[int(m) for m in d["periodos_meses"]],
            fatores_periodo={int(k): _dec(v) for k, v in d["fatores_periodo"].items()},
            treinamentos={
                prod: {
                    "horas": int(t["horas"]),
                    "precos_lista": {tipo: _dec(p) for tipo, p in t["precos_lista"].items()},
                    # False = valor já é o preço final em EUR (impostos à parte), sem os 5%
                    "aplicar_fator_brasil": bool(t.get("aplicar_fator_brasil", True)),
                }
                for prod, t in d["treinamentos"].items()
            },
            responsaveis={k: ResponsavelDPR(**v) for k, v in d["responsaveis"].items()},
            assinatura=Assinatura(**d["assinatura"]),
        )
        faltando = [m for m in params.periodos_meses if m not in params.fatores_periodo]
        if faltando:
            raise ValueError(f"Sem fator de período para: {faltando} meses")
        for tipo in ("novo", "renovacao"):
            params.reajuste_lista.setdefault(tipo, Decimal("0"))
        return params
