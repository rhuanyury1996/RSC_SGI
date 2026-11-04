import django.core.validators
from django.db import migrations, models

STATUS = [
    ("nao_iniciado", "Não iniciado", "#FFC53D"),
    ("organizando", "Organizando", "#0091FF"),
    ("executando", "Executando", "#0091FF"),
    ("em_revisao", "Em revisão", "#FFC53D"),
    ("liberado", "Liberado", "#1090E0"),
    ("realizado", "Realizado", "#30A46C"),
    ("complete", "Complete", "#008844"),
]
PRIORIDADES = [
    ("urgente", "Urgente", "#F50000"),
    ("alta", "Alta", "#FFCC00"),
    ("media", "Normal", "#6FDDFF"),
    ("baixa", "Baixa", "#D8D8D8"),
    ("nenhuma", "Sem prioridade", "#B9BEC7"),
]


def popular(apps, schema_editor):
    AparenciaStatus = apps.get_model("atividades", "AparenciaStatus")
    AparenciaPrioridade = apps.get_model("atividades", "AparenciaPrioridade")
    for ordem, (chave, nome, cor) in enumerate(STATUS):
        AparenciaStatus.objects.get_or_create(
            status=chave, defaults={"nome": nome, "cor": cor, "ordem": ordem}
        )
    for ordem, (chave, nome, cor) in enumerate(PRIORIDADES):
        AparenciaPrioridade.objects.get_or_create(
            prioridade=chave, defaults={"nome": nome, "cor": cor, "ordem": ordem}
        )


COR = [django.core.validators.RegexValidator("^#[0-9A-Fa-f]{6}$", "Use uma cor no formato #RRGGBB.")]


class Migration(migrations.Migration):
    dependencies = [
        ("atividades", "0012_sessao_manual"),
    ]

    operations = [
        migrations.CreateModel(
            name="AparenciaStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[(c, n) for c, n, _ in STATUS], max_length=20, unique=True, verbose_name="Status")),
                ("nome", models.CharField(max_length=40, verbose_name="Nome exibido")),
                ("cor", models.CharField(default="#87909E", max_length=7, validators=COR, verbose_name="Cor")),
                ("ordem", models.PositiveSmallIntegerField(default=0, help_text="Posição no fluxo (colunas e grupos).", verbose_name="Ordem")),
            ],
            options={
                "verbose_name": "Status: nome e cor",
                "verbose_name_plural": "Status: nomes e cores",
                "ordering": ["ordem", "id"],
            },
        ),
        migrations.CreateModel(
            name="AparenciaPrioridade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("prioridade", models.CharField(choices=[(c, n) for c, n, _ in PRIORIDADES], max_length=10, unique=True, verbose_name="Prioridade")),
                ("nome", models.CharField(max_length=40, verbose_name="Nome exibido")),
                ("cor", models.CharField(default="#B9BEC7", max_length=7, validators=COR, verbose_name="Cor da bandeira")),
                ("ordem", models.PositiveSmallIntegerField(default=0, verbose_name="Ordem")),
            ],
            options={
                "verbose_name": "Prioridade: nome e cor da bandeira",
                "verbose_name_plural": "Prioridades: nomes e cores das bandeiras",
                "ordering": ["ordem", "id"],
            },
        ),
        migrations.RunPython(popular, migrations.RunPython.noop),
    ]
