from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0024_empresa_dados_proposta"),
    ]

    operations = [
        migrations.AddField(
            model_name="oportunidade",
            name="custos_terceiros",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Até 5 terceiros: lista de {nome, valor}.",
                verbose_name="Custos com terceiros",
            ),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="custo_viagem",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Custo com viagem",
            ),
        ),
    ]
