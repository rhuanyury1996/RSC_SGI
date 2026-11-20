"""Cria ou atualiza o estudo PROX a partir do JSON local (fora do Git)."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from crm.models import Empresa
from tecnico.models import EstudoClassificacao, StatusEstudo

LIMITE_ESTADO_BYTES = 5 * 1024 * 1024


class Command(BaseCommand):
    help = "Carrega o estudo PROX (planta piloto, refazer RT-0001) no Setor Técnico."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", default="", help="JSON do estudo. Padrão: tecnico/dados_estudos/prox.json")
        parser.add_argument(
            "--com-produtos-puros",
            action="store_true",
            help="Inclui também as fontes dos produtos puros (balança e exaustor).",
        )

    def handle(self, *args, **opts):
        caminho = Path(opts["arquivo"]) if opts["arquivo"] else Path(settings.BASE_DIR) / "tecnico" / "dados_estudos" / "prox.json"
        if not caminho.is_file():
            raise CommandError(
                f"Arquivo não encontrado: {caminho}. Os dados do cliente ficam nessa pasta, que não entra no Git."
            )
        estado = json.loads(caminho.read_text(encoding="utf-8"))
        if opts["com_produtos_puros"]:
            extras = estado.pop("fontes_puros", None)
            if not extras:
                raise CommandError("O JSON não traz fontes_puros.")
            estado["fontes"] = list(estado.get("fontes") or []) + list(extras)
        else:
            estado.pop("fontes_puros", None)
        self._validar(estado)

        cab = estado.get("estudo") or {}
        nome = (cab.get("projeto") or "").strip()
        if not nome:
            raise CommandError("estado.estudo.projeto está vazio.")
        empresa = Empresa.objects.filter(nome__icontains="PROX DO BRASIL").order_by("id").first()
        if empresa is None:
            empresa = Empresa.objects.filter(nome__icontains="PROX").order_by("id").first()

        estudo = EstudoClassificacao.objects.filter(nome=nome[:200]).first()
        criado = estudo is None
        if criado:
            estudo = EstudoClassificacao(nome=nome[:200], status=StatusEstudo.ELABORACAO)
        estudo.cliente = (cab.get("cliente") or "PROX DO BRASIL").strip()[:200]
        estudo.revisao = str(cab.get("rev") or "0").strip()[:10]
        estudo.empresa = empresa
        estudo.estado = estado
        estudo.save()

        custom = estado.get("custom") or []
        misturas = [p for p in custom if p.get("origem") == "mistura"]
        pendentes = [p.get("nome") for p in custom if p.get("pendente")]
        pendentes += [f"sobrescrita {k}" for k, o in (estado.get("over") or {}).items() if isinstance(o, dict) and o.get("pendente")]
        self.stdout.write(self.style.SUCCESS("Estudo criado." if criado else "Estudo atualizado (sem duplicar)."))
        self.stdout.write(f"  nome: {estudo.nome}")
        self.stdout.write(f"  empresa CRM: {empresa.nome if empresa else 'não encontrada (não foi criada)'}")
        self.stdout.write(f"  produtos próprios: {len(custom)}")
        self.stdout.write(f"  misturas: {len(misturas)}")
        self.stdout.write(f"  fontes: {len(estado.get('fontes') or [])}")
        self.stdout.write(f"  pendentes: {len(pendentes)}")
        for nome_p in pendentes:
            self.stdout.write(f"    - {nome_p}")

    @staticmethod
    def _validar(estado):
        if not isinstance(estado, dict) or estado.get("v") != 1 or not isinstance(estado.get("fontes"), list):
            raise CommandError("Estado inválido: exige v = 1 e fontes em lista.")
        if not estado["fontes"]:
            raise CommandError("O estudo precisa de ao menos uma fonte.")
        bruto = json.dumps(estado, ensure_ascii=False).encode("utf-8")
        if len(bruto) > LIMITE_ESTADO_BYTES:
            raise CommandError("Estudo acima de 5 MB.")
