from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def criar_aliquota_padrao(apps, schema_editor):
    AliquotaImposto = apps.get_model("impostos", "AliquotaImposto")
    AliquotaImposto.objects.get_or_create(pk=1, defaults={"percentual": Decimal("18")})


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AliquotaImposto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "percentual",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("18"),
                        help_text="Percentual aplicado sobre o valor final fechado. Vale para os negócios ganhos a partir de agora; os já ganhos mantêm a alíquota da época.",
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0")),
                            django.core.validators.MaxValueValidator(Decimal("100")),
                        ],
                        verbose_name="Alíquota (%)",
                    ),
                ),
                (
                    "descricao",
                    models.CharField(
                        blank=True,
                        help_text="Opcional. Ex.: regime tributário ou composição dos impostos.",
                        max_length=160,
                        verbose_name="Descrição",
                    ),
                ),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="Atualizado em")),
            ],
            options={
                "verbose_name": "Alíquota de impostos",
                "verbose_name_plural": "Alíquota de impostos",
            },
        ),
        migrations.RunPython(criar_aliquota_padrao, migrations.RunPython.noop),
    ]
