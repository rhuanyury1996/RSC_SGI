from decimal import Decimal

from django.db import migrations, models
from django.db.models import Q


def gravar_aliquota_negocios_ganhos(apps, schema_editor):
    """Negócios já ganhos ficam com a alíquota de 18% que valia até agora."""
    Oportunidade = apps.get_model("crm", "Oportunidade")
    Oportunidade.objects.filter(
        Q(valor_final_fechado__isnull=False) | Q(oportunidade_pai__isnull=False),
        aliquota_impostos__isnull=True,
    ).update(aliquota_impostos=Decimal("18"))


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0025_custos_projeto"),
    ]

    operations = [
        migrations.AddField(
            model_name="oportunidade",
            name="aliquota_impostos",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Alíquota vigente quando a proposta foi ganha (Admin › Impostos).",
                max_digits=5,
                null=True,
                verbose_name="Alíquota de impostos (%)",
            ),
        ),
        migrations.RunPython(gravar_aliquota_negocios_ganhos, migrations.RunPython.noop),
    ]
