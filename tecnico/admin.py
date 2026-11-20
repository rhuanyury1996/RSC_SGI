from django.contrib import admin

from .models import EstudoClassificacao


@admin.register(EstudoClassificacao)
class EstudoClassificacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "cliente", "revisao", "status", "atualizado_por", "atualizado_em")
    list_filter = ("status",)
    search_fields = ("nome", "cliente")
    readonly_fields = ("criado_por", "atualizado_por", "criado_em", "atualizado_em")
    raw_id_fields = ("empresa",)
