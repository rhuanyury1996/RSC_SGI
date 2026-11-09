from django.db import migrations


class Migration(migrations.Migration):
    """Junta as duas migrações 0002 criadas em paralelo."""

    dependencies = [
        ("orcamentos", "0002_orcamento_categoria_licenca_orcamento_desconto_and_more"),
        ("orcamentos", "0002_revisao_e_historico_edicoes"),
    ]

    operations = []
