from django.contrib import admin

from .models import (
    Contato,
    Empresa,
    EtapaFunil,
    Funil,
    HistoricoOportunidade,
    ItemLista,
    Oportunidade,
)


class EtapaFunilInline(admin.TabularInline):
    model = EtapaFunil
    extra = 1


@admin.register(ItemLista)
class ItemListaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "ordem", "ativo")
    list_filter = ("tipo", "ativo")
    search_fields = ("nome",)
    ordering = ("tipo", "ordem", "nome")


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "nicho",
        "classificacao_unidade",
        "cidade",
        "estado",
        "telefone_portaria",
        "email_geral",
        "ativa",
    )
    search_fields = ("nome", "email_geral", "cidade", "site")
    list_filter = ("ativa", "estado", "nicho", "classificacao_unidade")
    autocomplete_fields = ("nicho",)


@admin.register(Contato)
class ContatoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sobrenome",
        "empresa",
        "email",
        "telefone_whatsapp",
        "responsavel",
        "ativo",
    )
    search_fields = ("nome", "sobrenome", "email", "empresa__nome")
    list_filter = ("ativo", "empresa", "responsavel")
    autocomplete_fields = ("empresa", "responsavel")


@admin.register(Funil)
class FunilAdmin(admin.ModelAdmin):
    list_display = ("nome", "cliente_rsc", "tipo", "ordem", "ativo")
    search_fields = ("nome", "cliente_rsc__nome")
    list_filter = ("ativo", "tipo")
    ordering = ("cliente_rsc__nome", "ordem")
    autocomplete_fields = ("cliente_rsc",)
    readonly_fields = ("ordem",)
    inlines = [EtapaFunilInline]

class HistoricoInline(admin.TabularInline):
    model = HistoricoOportunidade
    extra = 0
    readonly_fields = ("tipo", "descricao", "etapa_de", "etapa_para", "autor", "criado_em")
    can_delete = False


@admin.register(Oportunidade)
class OportunidadeAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "empresa",
        "funil",
        "etapa",
        "temperatura",
        "origem",
        "valor",
        "responsavel",
    )
    list_filter = ("funil", "etapa", "temperatura", "origem")
    search_fields = ("titulo", "empresa__nome", "contato_nome", "contato_email")
    autocomplete_fields = ("empresa", "contato", "responsavel", "funil")
    inlines = [HistoricoInline]
