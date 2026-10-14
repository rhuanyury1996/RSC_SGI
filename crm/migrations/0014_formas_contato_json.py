from django.db import migrations, models


def preparar_json(apps, schema_editor):
    """Normaliza valores vazios/inválidos para JSON array antes do cast."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE crm_oportunidade
            SET formas_contato = '[]'
            WHERE formas_contato IS NULL
               OR btrim(formas_contato) = ''
               OR left(btrim(formas_contato), 1) NOT IN ('[', '{')
            """
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0013_fluxo_prospeccao_pipefy"),
    ]

    operations = [
        migrations.RunPython(preparar_json, noop_reverse),
        migrations.AlterField(
            model_name="oportunidade",
            name="formas_contato",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Canais usados no 1º Contato: e-mail, telefone, WhatsApp.",
                verbose_name="Formas de contato",
            ),
        ),
    ]
