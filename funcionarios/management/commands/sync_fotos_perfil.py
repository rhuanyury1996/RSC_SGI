"""Gera foto_perfil_data a partir dos arquivos locais em MEDIA_ROOT."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from funcionarios.avatar import encode_avatar
from funcionarios.models import Funcionario


class Command(BaseCommand):
    help = "Converte fotos de perfil em disco para data URI no banco."

    def handle(self, *args, **options):
        media = Path(settings.MEDIA_ROOT)
        updated = 0
        missing = 0
        for funcionario in Funcionario.objects.exclude(foto_perfil="").exclude(
            foto_perfil__isnull=True
        ):
            path = media / funcionario.foto_perfil.name
            if not path.exists():
                self.stderr.write(f"Arquivo ausente: {path}")
                missing += 1
                continue
            with path.open("rb") as fh:
                funcionario.foto_perfil_data = encode_avatar(fh)
            funcionario.save(update_fields=["foto_perfil_data"])
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(f"OK {funcionario.nome_completo} ({path.name})")
            )
        self.stdout.write(f"Atualizados: {updated} · Ausentes: {missing}")
