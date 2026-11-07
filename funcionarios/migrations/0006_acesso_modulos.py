from django.db import migrations, models

NIVEIS = [("editar", "Ver e editar"), ("ver", "Só ver"), ("nenhum", "Sem acesso")]


def campo(rotulo):
    return models.CharField(rotulo, max_length=10, choices=NIVEIS, default="editar")


class Migration(migrations.Migration):

    dependencies = [
        ("funcionarios", "0005_foto_perfil_data"),
    ]

    operations = [
        migrations.AddField("funcionario", "acesso_comercial", campo("Comercial (CRM)")),
        migrations.AddField("funcionario", "acesso_orcamentos", campo("Orçamentos")),
        migrations.AddField("funcionario", "acesso_atividades", campo("Atividades")),
        migrations.AddField("funcionario", "acesso_apontamentos", campo("Apontamentos")),
        migrations.AddField("funcionario", "acesso_calendario", campo("Calendário")),
        migrations.AddField("funcionario", "acesso_informativos", campo("Informativos")),
        migrations.AddField("funcionario", "acesso_pagamentos", campo("Pagamentos")),
        migrations.CreateModel(
            name="AcessoModulo",
            fields=[],
            options={
                "verbose_name": "Acesso aos módulos",
                "verbose_name_plural": "Acessos aos módulos",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("funcionarios.funcionario",),
        ),
    ]
