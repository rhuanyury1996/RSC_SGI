import django.db.models.deletion
from django.db import migrations, models


def popular_status(apps, schema_editor):
    AtividadeDiaria = apps.get_model("atividades", "AtividadeDiaria")
    for item in AtividadeDiaria.objects.all().iterator():
        item.status = "realizado" if item.concluida else "nao_iniciado"
        if item.criado_por_id is None:
            item.criado_por_id = item.responsavel_id
        item.save(update_fields=["status", "criado_por"])


class Migration(migrations.Migration):

    dependencies = [
        ("funcionarios", "0001_initial"),
        ("atividades", "0002_prioridade_ordem_concluida_em"),
    ]

    operations = [
        migrations.RenameField(
            model_name="atividadediaria",
            old_name="funcionario",
            new_name="responsavel",
        ),
        migrations.RenameField(
            model_name="atividadediaria",
            old_name="data",
            new_name="planejado_para",
        ),
        migrations.AlterField(
            model_name="atividadediaria",
            name="planejado_para",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Dia no planner.",
                null=True,
                verbose_name="Planejado para",
            ),
        ),
        migrations.AlterField(
            model_name="atividadediaria",
            name="responsavel",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="atividades",
                to="funcionarios.funcionario",
                verbose_name="Responsável",
            ),
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="criado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="atividades_criadas",
                to="funcionarios.funcionario",
                verbose_name="Criado por",
            ),
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="status",
            field=models.CharField(
                choices=[
                    ("nao_iniciado", "Não iniciado"),
                    ("executando", "Executando"),
                    ("em_revisao", "Em revisão"),
                    ("realizado", "Realizado"),
                ],
                db_index=True,
                default="nao_iniciado",
                max_length=20,
                verbose_name="Status",
            ),
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="data_vencimento",
            field=models.DateField(
                blank=True, null=True, verbose_name="Data de vencimento"
            ),
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="tempo_acumulado_segundos",
            field=models.PositiveIntegerField(
                default=0, verbose_name="Tempo acumulado (s)"
            ),
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="cronometro_inicio",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Cronômetro iniciado em"
            ),
        ),
        migrations.AlterField(
            model_name="atividadediaria",
            name="prioridade",
            field=models.CharField(
                choices=[
                    ("baixa", "Baixa"),
                    ("media", "Média"),
                    ("alta", "Alta"),
                    ("urgente", "Urgente"),
                ],
                default="media",
                max_length=10,
                verbose_name="Prioridade",
            ),
        ),
        migrations.AlterModelOptions(
            name="atividadediaria",
            options={
                "ordering": ["status", "ordem", "-criado_em"],
                "verbose_name": "Atividade",
                "verbose_name_plural": "Atividades",
            },
        ),
        migrations.RunPython(popular_status, migrations.RunPython.noop),
    ]
