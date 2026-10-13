from django.db import migrations, models


ORDEM = {
    "pre_vendas": 0,
    "negociacoes": 1,
    "pos_vendas": 2,
}


def preencher_ordem(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    for funil in Funil.objects.all():
        funil.ordem = ORDEM.get(funil.tipo, 9)
        funil.save(update_fields=["ordem"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0009_funil_uniq_cliente_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="funil",
            name="ordem",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Sequência fixa: pré-vendas (0) → negociações (1) → pós-vendas (2).",
                verbose_name="Ordem no fluxo",
            ),
        ),
        migrations.AlterModelOptions(
            name="funil",
            options={
                "ordering": ["cliente_rsc__nome", "ordem", "nome"],
                "verbose_name": "Funil",
                "verbose_name_plural": "Funis",
            },
        ),
        migrations.RunPython(preencher_ordem, noop_reverse),
    ]
