from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import AliquotaImposto


@admin.register(AliquotaImposto)
class AliquotaImpostoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "descricao", "atualizado_em")
    fields = ("percentual", "descricao", "atualizado_em")
    readonly_fields = ("atualizado_em",)

    def has_add_permission(self, request):
        return not AliquotaImposto.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Registro único: abre direto a edição da alíquota
        obj, _ = AliquotaImposto.objects.get_or_create(pk=1)
        return redirect(reverse("admin:impostos_aliquotaimposto_change", args=[obj.pk]))
