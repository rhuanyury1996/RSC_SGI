import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("atividades", "0006_atividade_cliente_rsc"),
        ("funcionarios", "0002_jornada_trabalho"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atividadediaria",
            name="responsavel",
            field=models.ForeignKey(
                help_text="Dono da tarefa na equipe.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="atividades",
                to="funcionarios.funcionario",
                verbose_name="Responsável principal",
            ),
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="participantes",
            field=models.ManyToManyField(
                blank=True,
                help_text="Outras pessoas que trabalham nesta atividade em grupo.",
                related_name="atividades_participando",
                to="funcionarios.funcionario",
                verbose_name="Participantes",
            ),
        ),
    ]
