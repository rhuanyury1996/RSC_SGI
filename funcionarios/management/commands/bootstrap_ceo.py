import os
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from funcionarios.models import Cargo, CentroCusto, Funcionario, Setor


class Command(BaseCommand):
    help = "Cria o usuário CEO (nível mais alto) e vincula um perfil de funcionário."

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.getenv("CEO_USERNAME", "rfloriano")
        password = os.getenv("CEO_PASSWORD")

        if not password:
            self.stderr.write("Defina CEO_PASSWORD no arquivo .env")
            return

        existing = User.objects.filter(username__iexact=username).first()
        if existing and existing.username != username:
            username = existing.username

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "first_name": "R",
                "last_name": "Floriano",
            },
        )

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"CEO criado: {username}"))
        else:
            self.stdout.write(
                self.style.WARNING(f"CEO já existia; privilégios/senha atualizados: {username}")
            )

        funcionario, func_created = Funcionario.objects.get_or_create(
            usuario=user,
            defaults={
                "nome": user.first_name or "R",
                "sobrenome": user.last_name or "Floriano",
                "data_nascimento": date(1970, 1, 1),
                "cargo": Cargo.SOCIO,
                "setor": Setor.GESTAO,
                "centro_custo": CentroCusto.RSC,
                "ativo": True,
            },
        )

        if func_created:
            self.stdout.write(self.style.SUCCESS(f"Perfil de funcionário criado para {username}"))
        else:
            self.stdout.write(f"Perfil de funcionário já vinculado: {funcionario}")
