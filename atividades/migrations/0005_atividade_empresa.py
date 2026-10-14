import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("atividades", "0004_planner_produtividade_agua"),
        ("crm", "0021_servico_finalizado_atc_psc"),
    ]

    operations = [
        migrations.AddField(
            model_name="atividadediaria",
            name="empresa",
            field=models.ForeignKey(
                blank=True,
                help_text="Em branco = trabalho interno RSC. Preencha para apontar horas ao cliente.",
                limit_choices_to={"ativa": True},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="atividades",
                to="crm.empresa",
                verbose_name="Empresa",
            ),
        ),
    ]
