from django.db import migrations


ETAPAS_NEGOCIACOES = (
    "Proposta solicitada",
    "Negociação",
    "Contrato",
    "Fechamento",
)


def atualizar_etapas_negociacoes(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")
    Oportunidade = apps.get_model("crm", "Oportunidade")

    for funil in Funil.objects.filter(tipo="negociacoes"):
        EtapaFunil.objects.filter(funil=funil, nome="Proposta").update(
            nome="Proposta solicitada"
        )

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
        ("crm", "0015_motivo_falta_retorno_choices"),
    ]

    operations = [
        migrations.RunPython(atualizar_etapas_negociacoes, noop_reverse),
    ]
