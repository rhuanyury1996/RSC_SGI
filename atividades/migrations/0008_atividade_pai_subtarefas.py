import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("atividades", "0007_atividade_participantes"),
    ]

    operations = [
        migrations.AddField(
            model_name="atividadediaria",
            name="atividade_pai",
            field=models.ForeignKey(
                blank=True,
                help_text="Se preenchido, esta é uma subtarefa.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subtarefas",
                to="atividades.atividadediaria",
                verbose_name="Atividade principal",
            ),
        ),
    ]
