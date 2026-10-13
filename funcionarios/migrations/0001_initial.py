import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Funcionario",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nome", models.CharField(max_length=100, verbose_name="Nome")),
                ("sobrenome", models.CharField(max_length=100, verbose_name="Sobrenome")),
                ("data_nascimento", models.DateField(verbose_name="Data de nascimento")),
                (
                    "foto_perfil",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="funcionarios/fotos/",
                        verbose_name="Foto de perfil",
                    ),
                ),
                (
                    "cargo",
                    models.CharField(
                        choices=[
                            ("gerente", "Gerente"),
                            ("socio", "Sócio"),
                            ("supervisor", "Supervisor"),
                            ("executivo", "Executivo"),
                            ("estagiario", "Estagiário(a)"),
                        ],
                        max_length=20,
                        verbose_name="Cargo",
                    ),
                ),
                (
                    "centro_custo",
                    models.CharField(
                        choices=[
                            ("rsc", "RSC"),
                            ("blenddyn", "BlendDyn"),
                            ("veo", "VEO"),
                        ],
                        max_length=20,
                        verbose_name="Centro de custo",
                    ),
                ),
                ("ativo", models.BooleanField(default=True, verbose_name="Ativo")),
                (
                    "criado_em",
                    models.DateTimeField(auto_now_add=True, verbose_name="Criado em"),
                ),
                (
                    "atualizado_em",
                    models.DateTimeField(auto_now=True, verbose_name="Atualizado em"),
                ),
                (
                    "responde_a",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subordinados",
                        to="funcionarios.funcionario",
                        verbose_name="A quem responde",
                    ),
                ),
                (
                    "usuario",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="funcionario",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuário do sistema",
                    ),
                ),
            ],
            options={
                "verbose_name": "Funcionário",
                "verbose_name_plural": "Funcionários",
                "ordering": ["nome", "sobrenome"],
            },
        ),
    ]
