from django.db import migrations, models
import django.db.models.deletion


ETAPAS_POS_VENDAS = (
    "Acompanhando serviço",
    "Serviço finalizado",
    "Upsell",
    "Renovação",
)

RENOMEAR = {
    "Onboarding": "Acompanhando serviço",
    "Acompanhamento": "Acompanhando serviço",
}


def atualizar_etapas_pos_vendas(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")
    Oportunidade = apps.get_model("crm", "Oportunidade")

    for funil in Funil.objects.filter(tipo="pos_vendas"):
        for antigo, novo in RENOMEAR.items():
            EtapaFunil.objects.filter(funil=funil, nome=antigo).exclude(
                nome__in=ETAPAS_POS_VENDAS
            ).update(nome=novo)

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
        ("crm", "0019_proposta_ganha_campos"),
    ]

    operations = [
        migrations.AddField(
            model_name="oportunidade",
            name="oportunidade_pai",
            field=models.ForeignKey(
                blank=True,
                help_text="Card de Negociações que originou este acompanhamento em Pós-vendas.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cards_filhos",
                to="crm.oportunidade",
                verbose_name="Oportunidade origem",
            ),
        ),
        migrations.RunPython(atualizar_etapas_pos_vendas, noop_reverse),
    ]
