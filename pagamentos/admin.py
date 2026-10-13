from django.contrib import admin

from .models import Pagamento


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "tipo",
        "valor",
        "data_vencimento",
        "status",
        "funcionario",
    )
    list_filter = ("tipo", "status", "data_vencimento")
    search_fields = ("descricao", "funcionario__nome", "funcionario__sobrenome")
