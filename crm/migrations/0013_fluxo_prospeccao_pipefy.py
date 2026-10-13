from django.db import migrations, models
import django.db.models.deletion


ETAPAS = (
    "Captura",
    "1º Contato",
    "Retornar contato",
    "Envio de material | Reunião",
    "Follow Up",
    "Sem oportunidade",
    "Concluído",
)

RENOMEAR = {
    "Lead": "Captura",
    "Contato inicial": "1º Contato",
    "Qualificação": "1º Contato",
    "Agendamento": "Envio de material | Reunião",
    "Agendar reunião": "Envio de material | Reunião",
    "Stand-by": "Follow Up",
    "Sem oportunidade no momento ou solicitada proposta": "Sem oportunidade",
}


def sincronizar_etapas(apps, schema_editor):
    Funil = apps.get_model("crm", "Funil")
    EtapaFunil = apps.get_model("crm", "EtapaFunil")
    Oportunidade = apps.get_model("crm", "Oportunidade")

    for funil in Funil.objects.filter(tipo="pre_vendas"):
        for antigo, novo in RENOMEAR.items():
            EtapaFunil.objects.filter(funil=funil, nome=antigo).update(nome=novo)

        existentes = {e.nome: e for e in EtapaFunil.objects.filter(funil=funil)}
        captura = None
        for idx, nome in enumerate(ETAPAS):
            etapa = existentes.pop(nome, None)
            if etapa is None:
                etapa = EtapaFunil.objects.create(funil=funil, nome=nome, ordem=idx)
            else:
                if etapa.ordem != idx:
                    etapa.ordem = idx
                    etapa.save(update_fields=["ordem"])
            if nome == "Captura":
                captura = etapa

        for etapa in list(existentes.values()):
            if etapa.nome in ETAPAS:
                continue
            if Oportunidade.objects.filter(etapa=etapa).exists() and captura:
                Oportunidade.objects.filter(etapa=etapa).update(etapa=captura)
            etapa.delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0012_card_pre_vendas"),
    ]

    operations = [
        migrations.AddField(
            model_name="oportunidade",
            name="contato_sucesso",
            field=models.BooleanField(blank=True, null=True, verbose_name="Contato com sucesso?"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="existe_demanda",
            field=models.BooleanField(blank=True, null=True, verbose_name="Existe alguma demanda?"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="dores_identificadas",
            field=models.TextField(blank=True, verbose_name="Dores identificadas"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="data_retorno_envio",
            field=models.DateField(blank=True, null=True, verbose_name="Data de retorno / Envio"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="formas_contato",
            field=models.CharField(blank=True, max_length=200, verbose_name="Formas de contato"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="motivo_falta_retorno",
            field=models.TextField(blank=True, verbose_name="Motivo da falta de retorno"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="motivo_sem_oportunidade",
            field=models.TextField(blank=True, verbose_name="Motivo da falta de oportunidade"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="escopo_solicitado",
            field=models.TextField(blank=True, verbose_name="Escopo solicitado"),
        ),
        migrations.AddField(
            model_name="oportunidade",
            name="funil_venda",
            field=models.ForeignKey(
                blank=True,
                help_text="Funil de negociação para o qual o lead será encaminhado ao concluir.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="leads_origem_pre_vendas",
                to="crm.funil",
                verbose_name="Funil de venda",
            ),
        ),
        migrations.AlterField(
            model_name="oportunidade",
            name="data_retorno",
            field=models.DateField(blank=True, null=True, verbose_name="Data de retorno"),
        ),
        migrations.RunPython(sincronizar_etapas, noop_reverse),
    ]
