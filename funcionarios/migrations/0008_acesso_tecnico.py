from django.db import migrations, models

NIVEIS = [("editar", "Ver e editar"), ("ver", "Só ver"), ("nenhum", "Sem acesso")]


class Migration(migrations.Migration):

    dependencies = [
        ("funcionarios", "0007_acesso_financeiro"),
    ]

    operations = [
        migrations.AddField(
            "funcionario",
            "acesso_tecnico",
            models.CharField("Setor Técnico", max_length=10, choices=NIVEIS, default="editar"),
        ),
    ]
