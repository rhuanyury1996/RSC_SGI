from django.core.management.base import BaseCommand

from crm.gmail_sync import sincronizar_todas_contas


class Command(BaseCommand):
    help = (
        "Lê Gmail das contas Google vinculadas e cria cards de prospecção "
        "para o assunto/label configurados."
    )

    def handle(self, *args, **options):
        resultado = sincronizar_todas_contas()
        self.stdout.write(
            self.style.SUCCESS(
                "Gmail sync: "
                f"{resultado['usuarios']} usuário(s), "
                f"{resultado['criados']} criado(s), "
                f"{resultado['ignorados']} ignorado(s), "
                f"{resultado['erros']} erro(s)."
            )
        )
