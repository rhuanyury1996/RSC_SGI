from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("funcionarios", "0005_foto_perfil_data"),
        ("atividades", "0008_atividade_pai_subtarefas"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessaoTempoAtividade",
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
                ("inicio", models.DateTimeField(verbose_name="Início")),
                ("fim", models.DateTimeField(blank=True, null=True, verbose_name="Fim")),
                ("segundos", models.PositiveIntegerField(default=0, verbose_name="Segundos")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "atividade",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessoes_tempo",
                        to="atividades.atividadediaria",
                        verbose_name="Atividade",
                    ),
                ),
                (
                    "funcionario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessoes_tempo_atividade",
                        to="funcionarios.funcionario",
                        verbose_name="Funcionário",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sessão de tempo",
                "verbose_name_plural": "Sessões de tempo",
                "ordering": ["-inicio"],
                "indexes": [
                    models.Index(
                        fields=["funcionario", "inicio"],
                        name="atividades__funcion_7f2a1c_idx",
                    ),
                    models.Index(
                        fields=["atividade", "inicio"],
                        name="atividades__atividad_9c4e2b_idx",
                    ),
                ],
            },
        ),
    ]
