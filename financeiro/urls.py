from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.dashboard, name="painel"),
    path("filtro/entidade/", views.set_entity_filter, name="filtro_entidade"),
    path("lancamentos/", views.transaction_list, name="lancamentos"),
    path("lancamentos/exportar.xlsx", views.transaction_export_xlsx, name="exportar"),
    path("lancamentos/novo/", views.entry_hub, name="novo"),
    path("lancamentos/criar/", views.transaction_create, name="criar"),
    path("lancamentos/<int:pk>/editar/", views.transaction_edit, name="editar"),
    path("lancamentos/<int:pk>/status/", views.transaction_toggle_status, name="status"),
    path("lancamentos/<int:pk>/excluir/", views.transaction_delete, name="excluir"),
    path("lancamentos/<int:pk>/consolidar/", views.transaction_consolidate, name="consolidar"),
]
