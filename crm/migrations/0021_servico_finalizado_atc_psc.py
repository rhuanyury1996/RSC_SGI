from django.db import migrations, models


ETAPAS_POS_VENDAS = (
    "Acompanhando serviço",
    "Serviço finalizado",
    "Pós-venda finalizado",
    "Upsell",
    "Renovação",
)


def sincronizar_pos_venda_finalizado(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")
    Oportunidade = apps.get_model("crm", "Oportunidade")

    for funil in Funil.objects.filter(tipo="pos_vendas"):
        existentes = {e.nome: e for e in EtapaFunil.objects.filter(funil=funil)}
        oficiais = set(ETAPAS_POS_VENDAS)
        for idx, nome in enumerate(ETAPAS_POS_VENDAS):
            etapa = existentes.pop(nome, None)
            if etapa is None:
                EtapaFunil.objects.create(funil=funil, nome=nome, ordem=idx)
            elif etapa.ordem != idx:
                etapa.ordem = idx
                etapa.save(update_fields=["ordem"])
        for etapa in existentes.values():
            if etapa.nome in oficiais:
                continue
            if Oportunidade.objects.filter(etapa=etapa).exists():
                continue
            etapa.delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0020_pos_vendas_card_filho"),
    ]

    operations = [
        migrations.AddField(
            model_name="oportunidade",
            name="atc_enviado",
            field=models.BooleanField(default=False, verbose_name="ATC enviado"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="atc_enviado_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="ATC enviado em"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="psc_enviado",
            field=models.BooleanField(default=False, verbose_name="PSC enviado"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="psc_enviado_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="PSC enviado em"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="retorno_recebido",
            field=models.BooleanField(
                default=False,
                help_text="Se sim, o card vai para Pós-venda finalizado.",
                verbose_name="Retorno recebido",
            ),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="retorno_recebido_em",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Retorno recebido em"
            ),
        ),
        migrations.RunPython(sincronizar_pos_venda_finalizado, noop_reverse),
    ]
