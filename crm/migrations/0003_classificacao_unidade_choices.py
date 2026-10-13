from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_empresa_campos_listas"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="empresa",
            name="classificacao_unidade",
        ),
        migrations.AddField(
            model_name="empresa",
            name="classificacao_unidade",
            field=models.CharField(
                blank=True,
                choices=[
                    ("filial", "Filial"),
                    ("sede_corporativa", "Sede corporativa"),
                    ("matriz", "Matriz"),
                ],
                max_length=30,
                verbose_name="Classificação da unidade",
            ),
        ),
        migrations.AlterField(
            model_name="itemlista",
            name="tipo",
            field=models.CharField(
                choices=[("nicho_mercadologico", "Nicho mercadológico")],
                max_length=40,
                verbose_name="Tipo da lista",
            ),
        ),
    ]
