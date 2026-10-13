from django.db import migrations, models


def limpar_motivos(apps, schema_editor):
    Oportunidade = apps.get_model("crm", "Oportunidade")
    validos = {
        "nao_disponivel",
        "portaria",
        "ligacao",
        "sem_email",
    }
    mapa = {
        "não estava disponível": "nao_disponivel",
        "nao estava disponivel": "nao_disponivel",
        "portaria não pode passar contato": "portaria",
        "portaria nao pode passar contato": "portaria",
        "não completou a ligação": "ligacao",
        "nao completou a ligacao": "ligacao",
        "sem retorno de e-mail": "sem_email",
        "sem retorno de email": "sem_email",
    }
    for opp in Oportunidade.objects.exclude(motivo_falta_retorno=""):
        raw = (opp.motivo_falta_retorno or "").strip()
        if raw in validos:
            continue
        chave = mapa.get(raw.lower())
        opp.motivo_falta_retorno = chave or ""
        opp.save(update_fields=["motivo_falta_retorno"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0014_formas_contato_json"),
    ]

    operations = [
        migrations.RunPython(limpar_motivos, noop_reverse),
        migrations.AlterField(
            model_name="oportunidade",
            name="motivo_falta_retorno",
            field=models.CharField(
                blank=True,
                choices=[
                    ("nao_disponivel", "Não estava disponível"),
                    ("portaria", "Portaria não pode passar contato"),
                    ("ligacao", "Não completou a ligação"),
                    ("sem_email", "Sem retorno de e-mail"),
                ],
                max_length=40,
                verbose_name="Motivo da falta de retorno",
            ),
        ),
    ]
