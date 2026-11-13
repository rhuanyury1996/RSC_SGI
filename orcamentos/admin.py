from django.contrib import admin

from .models import Orcamento, TabelaParametros


@admin.register(TabelaParametros)
class TabelaParametrosAdmin(admin.ModelAdmin):
    list_display = ("ano", "versao", "atualizado_em", "atualizado_por")
    ordering = ("-ano",)

    @admin.display(description="Versão")
    def versao(self, obj: TabelaParametros) -> str:
        return obj.dados.get("versao_tabela", "")


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = ("numero", "data", "empresa", "escopo", "total_servicos", "status", "emitido_por")
    list_filter = ("status", "escopo", "data")
    search_fields = ("numero", "empresa__nome", "nome_arquivo")
    date_hierarchy = "data"
    ordering = ("-data", "-sequencial")
    exclude = ("arquivo",)
    readonly_fields = ("numero", "nome_arquivo", "criado_em")


from .models import OrcamentoRaven, TabelaRaven  # noqa: E402


@admin.register(TabelaRaven)
class TabelaRavenAdmin(admin.ModelAdmin):
    list_display = ("ano", "versao", "atualizado_em", "atualizado_por")
    ordering = ("-ano",)

    @admin.display(description="Versão")
    def versao(self, obj: TabelaRaven) -> str:
        return obj.dados.get("versao_tabela", "")


@admin.register(OrcamentoRaven)
class OrcamentoRavenAdmin(admin.ModelAdmin):
    list_display = ("numero", "data", "empresa", "tipo_cliente", "plano_nome", "total", "status", "login_liberado_em", "emitido_por")
    list_filter = ("status", "tipo_cliente", "plano", "data")
    search_fields = ("numero", "empresa__nome", "nome_arquivo")
    date_hierarchy = "data"
    ordering = ("-data", "-sequencial")
    exclude = ("arquivo",)
    readonly_fields = ("numero", "nome_arquivo", "criado_em")
