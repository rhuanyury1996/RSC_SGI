from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("atividades", "0010_soft_delete_historico"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atividadediaria",
            name="status",
            field=models.CharField(
                choices=[
                    ("nao_iniciado", "Não iniciado"),
                    ("organizando", "Organizando"),
                    ("executando", "Executando"),
                    ("em_revisao", "Em revisão"),
                    ("liberado", "Liberado"),
                    ("realizado", "Realizado"),
                    ("complete", "Complete"),
                ],
                db_index=True,
                default="nao_iniciado",
                max_length=20,
                verbose_name="Status",
            ),
        ),
        migrations.AlterField(
            model_name="atividadediaria",
            name="prioridade",
            field=models.CharField(
                choices=[
                    ("urgente", "Urgente"),
                    ("alta", "Alta"),
                    ("media", "Normal"),
                    ("baixa", "Baixa"),
                    ("nenhuma", "Sem prioridade"),
                ],
                default="media",
                max_length=10,
                verbose_name="Prioridade",
            ),
        ),
    ]
