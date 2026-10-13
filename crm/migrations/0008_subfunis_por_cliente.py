from django.db import migrations, models
import django.db.models.deletion


ETAPAS_POR_TIPO = {
    "pre_vendas": ("Lead", "Contato inicial", "Qualificação", "Agendamento"),
    "negociacoes": ("Proposta", "Negociação", "Contrato", "Fechamento"),
    "pos_vendas": ("Onboarding", "Acompanhamento", "Upsell", "Renovação"),
}

TIPOS = ("pre_vendas", "negociacoes", "pos_vendas")

TIPO_LABEL = {
    "pre_vendas": "Pré-vendas",
    "negociacoes": "Negociações",
    "pos_vendas": "Pós-vendas",
}


def converter_para_subfunis(apps, schema_editor):
    ItemLista = apps.get_model("crm", "ItemLista")
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")

    # Funis já ligados a cliente: marcar como pré-vendas se ainda não tipados
    for funil in Funil.objects.filter(cliente_rsc__isnull=False):
        if not funil.tipo:
            funil.tipo = "pre_vendas"
        if funil.cliente_rsc_id:
            label = TIPO_LABEL.get(funil.tipo, funil.tipo)
            funil.nome = f"{funil.cliente_rsc.nome} · {label}"
            funil.save(update_fields=["tipo", "nome"])

    # Funis órfãos sem cliente: manter, apenas garantir tipo
    Funil.objects.filter(tipo="").update(tipo="pre_vendas")
    Funil.objects.filter(tipo__isnull=True).update(tipo="pre_vendas")

    for cliente in ItemLista.objects.filter(tipo="clientes_rsc"):
        existentes = {
            f.tipo: f for f in Funil.objects.filter(cliente_rsc=cliente)
        }
        # Se houver exatamente 1 funil sem tipagem útil, já foi setado pre_vendas acima
        for tipo in TIPOS:
            funil = existentes.get(tipo)
            if funil is None:
                funil = Funil.objects.create(
                    nome=f"{cliente.nome} · {TIPO_LABEL[tipo]}",
                    descricao=f"{TIPO_LABEL[tipo]} — {cliente.nome}",
                    cliente_rsc=cliente,
                    tipo=tipo,
                    ativo=cliente.ativo,
                )
            if not EtapaFunil.objects.filter(funil=funil).exists():
                EtapaFunil.objects.bulk_create(
                    [
                        EtapaFunil(funil=funil, nome=nome, ordem=idx)
                        for idx, nome in enumerate(ETAPAS_POR_TIPO[tipo])
                    ]
                )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0007_sincronizar_funis_clientes"),
    ]

    operations = [
        migrations.AddField(
            model_name="funil",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("pre_vendas", "Pré-vendas"),
                    ("negociacoes", "Negociações"),
                    ("pos_vendas", "Pós-vendas"),
                ],
                default="pre_vendas",
                max_length=20,
                verbose_name="Subfunil",
            ),
        ),
        migrations.AlterField(
            model_name="funil",
            name="cliente_rsc",
            field=models.ForeignKey(
                blank=True,
                help_text="Cliente RSC dono deste funil de controle.",
                limit_choices_to={"tipo": "clientes_rsc"},
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="funis",
                to="crm.itemlista",
                verbose_name="Cliente RSC",
            ),
        ),
        migrations.AlterModelOptions(
            name="funil",
            options={
                "ordering": ["cliente_rsc__nome", "tipo", "nome"],
                "verbose_name": "Funil",
                "verbose_name_plural": "Funis",
            },
        ),
        migrations.RunPython(converter_para_subfunis, noop_reverse),
    ]
