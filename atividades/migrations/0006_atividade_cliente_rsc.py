import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("atividades", "0005_atividade_empresa"),
        ("crm", "0021_servico_finalizado_atc_psc"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="atividadediaria",
            name="empresa",
        ),
        migrations.AddField(
            model_name="atividadediaria",
            name="cliente_rsc",
            field=models.ForeignKey(
                blank=True,
                help_text="Em branco = RSC. Opções = Clientes RSC (ex.: DPR, OTILINE, CRITEQ).",
                limit_choices_to={"ativo": True, "tipo": "clientes_rsc"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="atividades",
                to="crm.itemlista",
                verbose_name="Empresa",
            ),
        ),
    ]
