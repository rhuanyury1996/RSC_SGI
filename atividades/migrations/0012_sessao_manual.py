from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("atividades", "0011_status_fluxo_completo"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessaotempoatividade",
            name="manual",
            field=models.BooleanField(
                default=False,
                help_text="Tempo informado à mão (ex.: esqueceu de ligar o cronômetro).",
                verbose_name="Lançado manualmente",
            ),
        ),
    ]
