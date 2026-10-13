from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0008_subfunis_por_cliente"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="funil",
            constraint=models.UniqueConstraint(
                condition=models.Q(cliente_rsc__isnull=False),
                fields=("cliente_rsc", "tipo"),
                name="uniq_funil_cliente_tipo",
            ),
        ),
    ]
