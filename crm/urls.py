from django.urls import path

from . import views

urlpatterns = [
    path("", views.hub, name="crm"),
    path("empresas/", views.empresas, name="crm_empresas"),
    path("empresas/cnpj/", views.consultar_cnpj_view, name="crm_consultar_cnpj"),
    path("empresas/<int:pk>/", views.empresa_editar, name="crm_empresa_editar"),
    path("contatos/", views.contatos, name="crm_contatos"),
    path("contatos/<int:pk>/", views.contato_editar, name="crm_contato_editar"),
    path("importar/", views.importar_base, name="crm_importar_base"),
    path("funis/", views.funis, name="crm_funis"),
    path("funis/<int:pk>/", views.funil_detalhe, name="crm_funil_detalhe"),
    path("funis/<int:pk>/mover/", views.funil_mover_card, name="crm_funil_mover"),
    path("listas/", views.listas, name="crm_listas"),
    path(
        "api/prospeccao-email/",
        views.webhook_prospeccao_gmail,
        name="crm_webhook_prospeccao_gmail",
    ),
    path(
        "api/sincronizar-gmail/",
        views.webhook_sincronizar_gmail_oauth,
        name="crm_webhook_sincronizar_gmail",
    ),
    path("gmail/conectar/", views.gmail_conectar, name="crm_gmail_conectar"),
    path("gmail/callback/", views.gmail_callback, name="crm_gmail_callback"),
    path("gmail/adiar/", views.gmail_adiar_popup, name="crm_gmail_adiar"),
    path("gmail/desconectar/", views.gmail_desconectar, name="crm_gmail_desconectar"),
]
