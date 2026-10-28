from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0021_servico_finalizado_atc_psc"),
    ]

    operations = [
        migrations.AddField(
            model_name="oportunidade",
            name="percentual_comissao",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Informe o % de comissão sobre o valor final fechado.",
                max_digits=5,
                null=True,
                verbose_name="Percentual de comissão (%)",
            ),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="percentual_bonus",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="De 12% a 35% da comissão, conforme performance.",
                max_digits=5,
                null=True,
                verbose_name="Percentual de bônus do agente (%)",
            ),
        ),
        migrations.AlterField(
            model_name="oportunidade",
            name="fator_comissionamento",
            field=models.CharField(
                blank=True,
                choices=[
                    ("passivo", "Comissionamento passivo - 4,5%"),
                    ("ativo", "Comissionamento ativo - 7,0%"),
                    ("guarda_chuva", "Comissionamento guarda-chuva (MBRF) - 10,0%"),
                ],
                help_text="Legado. Preferir percentual_comissao informado manualmente.",
                max_length=20,
                verbose_name="Fator de comissionamento (legado)",
            ),
        ),
        migrations.AlterField(
            model_name="oportunidade",
            name="comissao",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Calculada: percentual × valor final fechado.",
                max_digits=12,
                null=True,
                verbose_name="Comissão",
            ),
        ),
        migrations.AlterField(
            model_name="oportunidade",
            name="bonus_agente",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Calculado: percentual de bônus × comissão (12%–35%).",
                max_digits=12,
                null=True,
                verbose_name="Bônus para agente",
            ),
        ),
    ]
