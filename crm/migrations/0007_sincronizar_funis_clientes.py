from django.db import migrations


ETAPAS_PADRAO = (
    "Prospecção",
    "Qualificação",
    "Proposta",
    "Negociação",
    "Fechamento",
)


def sincronizar_funis(apps, schema_editor):
    ItemLista = apps.get_model("crm", "ItemLista")
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")

    for cliente in ItemLista.objects.filter(tipo="clientes_rsc"):
        funil, created = Funil.objects.get_or_create(
            cliente_rsc=cliente,
            defaults={
                "nome": cliente.nome,
                "descricao": f"Área de controle do cliente {cliente.nome}.",
                "ativo": cliente.ativo,
            },
        )
        if not created:
            updates = []
            if funil.nome != cliente.nome:
                funil.nome = cliente.nome
                updates.append("nome")
            if funil.ativo != cliente.ativo:
                funil.ativo = cliente.ativo
                updates.append("ativo")
            if updates:
                funil.save(update_fields=updates)
        if not EtapaFunil.objects.filter(funil=funil).exists():
            EtapaFunil.objects.bulk_create(
                [
                    EtapaFunil(funil=funil, nome=nome, ordem=idx)
                    for idx, nome in enumerate(ETAPAS_PADRAO)
                ]
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0006_funil_cliente_rsc"),
    ]

    operations = [
        migrations.RunPython(sincronizar_funis, noop_reverse),
    ]
