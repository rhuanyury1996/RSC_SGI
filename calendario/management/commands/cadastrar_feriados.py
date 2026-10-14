from django.core.management.base import BaseCommand
from django.utils import timezone

from calendario.services_feriados import cadastrar_feriados_ano


class Command(BaseCommand):
    help = (
        "Cadastra feriados nacionais no calendário de cada colaborador ativo "
        "(crédito automático da jornada)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ano",
            type=int,
            default=None,
            help="Ano a cadastrar (padrão: ano atual).",
        )

    def handle(self, *args, **options):
        ano = options["ano"] or timezone.localdate().year
        resultado = cadastrar_feriados_ano(ano)
        self.stdout.write(
            self.style.SUCCESS(
                f"Feriados {ano}: {resultado['feriados']} datas · "
                f"{resultado['funcionarios']} colaborador(es) · "
                f"{resultado['criados']} criados · "
                f"{resultado['existentes']} já existiam."
            )
        )
