from django.db import migrations


ETAPAS_PRE_VENDAS = (
    "Captura",
    "Contato inicial",
    "Retornar contato",
    "Agendar reunião",
    "Stand-by",
    "Sem oportunidade no momento ou solicitada proposta",
)

RENOMEAR = {
    "Lead": "Captura",
    "Qualificação": "Retornar contato",
    "Agendamento": "Agendar reunião",
}


def atualizar_etapas_pre_vendas(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")
    Oportunidade = apps.get_model("crm", "Oportunidade")

    for funil in Funil.objects.filter(tipo="pre_vendas"):
        for antigo, novo in RENOMEAR.items():
            EtapaFunil.objects.filter(funil=funil, nome=antigo).update(nome=novo)

        existentes = {e.nome: e for e in EtapaFunil.objects.filter(funil=funil)}
        oficiais = set(ETAPAS_PRE_VENDAS)

        for idx, nome in enumerate(ETAPAS_PRE_VENDAS):
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
        ("crm", "0010_funil_ordem_fluxo"),
    ]

    operations = [
        migrations.RunPython(atualizar_etapas_pre_vendas, noop_reverse),
    ]
