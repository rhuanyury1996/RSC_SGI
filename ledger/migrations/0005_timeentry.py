# Generated manually for time tracking module

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ledger", "0004_projected_sale"),
        ("workspaces", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimeEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("work_date", models.DateField(db_index=True, verbose_name="Data")),
                (
                    "clock_in",
                    models.DateTimeField(blank=True, null=True, verbose_name="Entrada"),
                ),
                (
                    "lunch_out",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Saída almoço"
                    ),
                ),
                (
                    "lunch_in",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Retorno almoço"
                    ),
                ),
                (
                    "clock_out",
                    models.DateTimeField(blank=True, null=True, verbose_name="Saída"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="Observações")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="time_entries",
                        to="ledger.client",
                        verbose_name="Cliente",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="time_entries",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuário",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Apontamento",
                "verbose_name_plural": "Apontamentos",
                "ordering": ["-work_date", "-clock_in", "-id"],
                "indexes": [
                    models.Index(
                        fields=["workspace", "user", "work_date"],
                        name="ledger_time_workspa_b43e44_idx",
                    ),
                ],
            },
        ),
    ]
