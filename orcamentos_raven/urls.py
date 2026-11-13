from django.urls import path

from . import views

# Montado em /orcamentos/raven/ (mesmo controle de acesso do módulo Orçamentos).
urlpatterns = [
    path("", views.historico, name="orcamentos_raven"),
    path("novo/", views.novo, name="orcamento_raven_novo"),
    path("<int:pk>/", views.abrir, name="orcamento_raven_abrir"),
    path("<int:pk>/download/", views.download, name="orcamento_raven_download"),
    path("<int:pk>/status/", views.mudar_status, name="orcamento_raven_status"),
    path("<int:pk>/login/", views.liberar_login, name="orcamento_raven_login"),
    path("parametros/", views.parametros, name="orcamento_raven_parametros"),
    path("parametros/<int:ano>/", views.parametros_editar, name="orcamento_raven_parametros_editar"),
]
