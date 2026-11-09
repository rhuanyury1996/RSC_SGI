from django.apps import AppConfig


class LedgerConfig(AppConfig):
    """Modelos do Financeiro (vindos do Arcturus)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "ledger"
    label = "ledger"
    verbose_name = "Financeiro · Lançamentos"
