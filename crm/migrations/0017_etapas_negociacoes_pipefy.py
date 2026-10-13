from django.db import migrations


ETAPAS_NEGOCIACOES = (
    "Oportunidade confirmada",
    "Elaborando proposta",
    "Proposta enviada",
    "Follow Up",
    "Aguardando desfecho",
    "Proposta Perdida",
    "Proposta Ganha",
)

RENOMEAR = {
    "Proposta": "Oportunidade confirmada",
    "Proposta solicitada": "Oportunidade confirmada",
    "Negociação": "Elaborando proposta",
    "Contrato": "Proposta enviada",
    "Fechamento": "Proposta Ganha",
}


def atualizar_etapas_negociacoes(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")
    Oportunidade = apps.get_model("crm", "Oportunidade")

    for funil in Funil.objects.filter(tipo="negociacoes"):
        for antigo, novo in RENOMEAR.items():
            EtapaFunil.objects.filter(funil=funil, nome=antigo).exclude(
                nome__in=ETAPAS_NEGOCIACOES
            ).update(nome=novo)

        existentes = {e.nome: e for e in EtapaFunil.objects.filter(funil=funil)}
        oficiais = set(ETAPAS_NEGOCIACOES)

        for idx, nome in enumerate(ETAPAS_NEGOCIACOES):
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
        ("crm", "0016_etapas_negociacoes_proposta_solicitada"),
    ]

    operations = [
        migrations.RunPython(atualizar_etapas_negociacoes, noop_reverse),
    ]
