import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Orçamento RAVEN: tabela de planos por ano e propostas emitidas."""

    dependencies = [
        ("crm", "0024_empresa_dados_proposta"),
        ("funcionarios", "0005_foto_perfil_data"),
        ("orcamentos", "0003_merge_20261109"),
    ]

    operations = [
        migrations.CreateModel(
            name="TabelaRaven",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ano", models.PositiveSmallIntegerField(unique=True, verbose_name="Ano da tabela")),
                ("dados", models.JSONField(verbose_name="Parâmetros")),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "atualizado_por",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to="funcionarios.funcionario",
                    ),
                ),
            ],
            options={"verbose_name": "Tabela RAVEN", "verbose_name_plural": "Tabelas RAVEN", "ordering": ["-ano"]},
        ),
        migrations.CreateModel(
            name="OrcamentoRaven",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(max_length=20, unique=True, verbose_name="Número")),
                ("data", models.DateField(db_index=True, verbose_name="Data da proposta")),
                ("sequencial", models.PositiveSmallIntegerField(verbose_name="Sequencial do dia")),
                ("validade", models.DateField(verbose_name="Validade")),
                ("validade_dias", models.PositiveSmallIntegerField(default=30, verbose_name="Validade (dias)")),
                ("cliente", models.JSONField(verbose_name="Cliente (snapshot)")),
                ("contato_dados", models.JSONField(verbose_name="Contato (snapshot)")),
                (
                    "tipo_cliente",
                    models.CharField(
                        choices=[("industria", "Indústria"), ("consultoria", "Consultoria")],
                        max_length=12, verbose_name="Tipo de cliente",
                    ),
                ),
                ("plano", models.CharField(max_length=30, verbose_name="Plano")),
                ("plano_nome", models.CharField(max_length=60, verbose_name="Nome do plano")),
                ("usuarios", models.PositiveSmallIntegerField(default=0, verbose_name="Usuários simultâneos")),
                ("vigencia_meses", models.PositiveSmallIntegerField(default=0, verbose_name="Vigência (meses)")),
                ("trial", models.BooleanField(default=False, verbose_name="Trial")),
                ("valor_licenca", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("valor_tabela", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("implantacao", models.BooleanField(default=False, verbose_name="Implantação em campo")),
                ("valor_implantacao", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("horas_visita", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("cidade_visita", models.CharField(blank=True, max_length=120, verbose_name="Cidade/UF da visita")),
                ("horas_pacote", models.PositiveIntegerField(default=0, verbose_name="Pacote de horas")),
                ("valor_hora", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("valor_pacote", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "pagamento",
                    models.CharField(
                        choices=[("vista", "À vista (8% de desconto na licença)"), ("10x", "Parcelado em 10× no boleto")],
                        default="vista", max_length=6, verbose_name="Pagamento",
                    ),
                ),
                ("desconto", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Desconto à vista")),
                ("total", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Total")),
                ("linhas", models.JSONField(default=list, verbose_name="Linhas da proposta")),
                ("avisos", models.JSONField(blank=True, default=list)),
                ("versao_tabela", models.CharField(max_length=120)),
                ("nome_arquivo", models.CharField(max_length=200)),
                ("arquivo", models.BinaryField(verbose_name="Proposta (.html)")),
                (
                    "status",
                    models.CharField(
                        choices=[("emitida", "Emitida"), ("enviada", "Enviada"), ("aceita", "Aceita"), ("recusada", "Recusada")],
                        db_index=True, default="emitida", max_length=10,
                    ),
                ),
                ("historico_status", models.JSONField(blank=True, default=list)),
                ("aceite_em", models.DateTimeField(blank=True, null=True, verbose_name="Aceite em")),
                ("login_liberado_em", models.DateTimeField(blank=True, null=True, verbose_name="Login liberado em")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "contato",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orcamentos_raven", to="crm.contato",
                    ),
                ),
                (
                    "emitido_por",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orcamentos_raven_emitidos", to="funcionarios.funcionario",
                    ),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orcamentos_raven", to="crm.empresa",
                    ),
                ),
                (
                    "login_liberado_por",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+", to="funcionarios.funcionario",
                    ),
                ),
                (
                    "tabela",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="orcamentos",
                        to="orcamentos.tabelaraven",
                    ),
                ),
            ],
            options={"verbose_name": "Orçamento RAVEN", "verbose_name_plural": "Orçamentos RAVEN", "ordering": ["-data", "-sequencial"]},
        ),
    ]
