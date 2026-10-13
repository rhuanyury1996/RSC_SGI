from django.contrib import admin

from .models import Informativo


@admin.register(Informativo)
class InformativoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "autor", "publicado_em", "ativo")
    list_filter = ("categoria", "ativo", "publicado_em")
    search_fields = ("titulo", "conteudo")

    def save_model(self, request, obj, form, change):
        if not obj.autor_id:
            obj.autor = request.user
        super().save_model(request, obj, form, change)
