from django.urls import path

from . import views

urlpatterns = [
    path("", views.historico, name="orcamentos"),
    path("novo/", views.novo, name="orcamento_novo"),
    path("<int:pk>/", views.detalhe, name="orcamento_detalhe"),
    path("<int:pk>/editar/", views.editar, name="orcamento_editar"),
    path("<int:pk>/download/", views.download, name="orcamento_download"),
    path("<int:pk>/status/", views.mudar_status, name="orcamento_status"),
    path("parametros/", views.parametros, name="orcamento_parametros"),
    path("parametros/<int:ano>/", views.parametros_editar, name="orcamento_parametros_editar"),
    path("empresas/<int:empresa_id>/contatos/", views.contatos_json, name="orcamento_contatos_json"),
]
