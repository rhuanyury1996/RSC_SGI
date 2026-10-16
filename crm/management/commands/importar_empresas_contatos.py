"""
Importa bases Excel de empresas e contatos.

Uso:
  python manage.py importar_empresas_contatos \\
    --empresas "C:/Users/.../Base de empresas.xlsx" \\
    --contatos "C:/Users/.../Base de contatos.xlsx"
"""

from django.core.management.base import BaseCommand, CommandError

from crm.importacao import ImportacaoErro, importar_empresas_contatos


class Command(BaseCommand):
    help = "Importa empresas e contatos a partir de planilhas Excel."

    def add_arguments(self, parser):
        parser.add_argument("--empresas", type=str, required=True, help="XLSX de empresas")
        parser.add_argument("--contatos", type=str, required=True, help="XLSX de contatos")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula sem gravar no banco",
        )

    def handle(self, *args, **options):
        try:
            resultado = importar_empresas_contatos(
                options["empresas"],
                options["contatos"],
                dry_run=options["dry_run"],
            )
        except ImportacaoErro as exc:
            raise CommandError(str(exc)) from exc

        for aviso in resultado.avisos:
            self.stdout.write(self.style.WARNING(aviso))

        msg = resultado.mensagem()
        if options["dry_run"]:
            msg += " (dry-run)"
        self.stdout.write(self.style.SUCCESS(msg))
