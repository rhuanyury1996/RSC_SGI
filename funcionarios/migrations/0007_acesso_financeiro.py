from django.db import migrations, models

NIVEIS = [("editar", "Ver e editar"), ("ver", "Só ver"), ("nenhum", "Sem acesso")]


class Migration(migrations.Migration):

    dependencies = [
        ("funcionarios", "0006_acesso_modulos"),
    ]

    operations = [
        migrations.AddField(
            "funcionario",
            "acesso_financeiro",
            models.CharField("Financeiro", max_length=10, choices=NIVEIS, default="nenhum"),
        ),
    ]
