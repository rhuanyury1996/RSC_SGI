"""Cadastra/atualiza a tabela de planos RAVEN de um ano a partir de um JSON."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from orcamentos.models import TabelaRaven
from orcamentos.raven.calculo import ParametrosRaven

PADRAO = Path(__file__).resolve().parents[2] / "raven" / "parametros_2026.json"


class Command(BaseCommand):
    help = "Semeia a tabela de planos do orçamento RAVEN (padrão: 2026)."

    def add_arguments(self, parser):
        parser.add_argument("--ano", type=int, default=2026)
        parser.add_argument("--arquivo", type=str, default=str(PADRAO))
        parser.add_argument("--forcar", action="store_true", help="Sobrescreve a tabela se o ano já existir.")

    def handle(self, *args, **opts):
        caminho = Path(opts["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        try:
            ParametrosRaven.de_dict(dados)
        except (KeyError, ValueError, TypeError) as exc:
            raise CommandError(f"Parâmetros inválidos: {exc}") from exc
        ano = opts["ano"]
        if TabelaRaven.objects.filter(ano=ano).exists() and not opts["forcar"]:
            self.stdout.write(f"Tabela RAVEN de {ano} já existe. Use --forcar para sobrescrever.")
            return
        TabelaRaven.objects.update_or_create(ano=ano, defaults={"dados": dados})
        self.stdout.write(self.style.SUCCESS(f"Tabela RAVEN de {ano} gravada ({dados['versao_tabela']})."))
