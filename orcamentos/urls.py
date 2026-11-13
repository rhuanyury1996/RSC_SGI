from django.urls import path

from . import views, views_raven

urlpatterns = [
    path("", views.historico, name="orcamentos"),
    path("novo/", views.novo, name="orcamento_novo"),
    path("<int:pk>/download/", views.download, name="orcamento_download"),
    path("<int:pk>/status/", views.mudar_status, name="orcamento_status"),
    path("parametros/", views.parametros, name="orcamento_parametros"),
    path("parametros/<int:ano>/", views.parametros_editar, name="orcamento_parametros_editar"),
    path("empresas/<int:empresa_id>/contatos/", views.contatos_json, name="orcamento_contatos_json"),
    # RAVEN
    path("raven/", views_raven.historico, name="orcamentos_raven"),
    path("raven/novo/", views_raven.novo, name="orcamento_raven_novo"),
    path("raven/<int:pk>/", views_raven.abrir, name="orcamento_raven_abrir"),
    path("raven/<int:pk>/download/", views_raven.download, name="orcamento_raven_download"),
    path("raven/<int:pk>/status/", views_raven.mudar_status, name="orcamento_raven_status"),
    path("raven/<int:pk>/login/", views_raven.liberar_login, name="orcamento_raven_login"),
    path("raven/parametros/", views_raven.parametros, name="orcamento_raven_parametros"),
    path("raven/parametros/<int:ano>/", views_raven.parametros_editar, name="orcamento_raven_parametros_editar"),
]
