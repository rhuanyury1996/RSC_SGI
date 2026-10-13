from django.urls import path

from . import views

urlpatterns = [
    path("", views.hub, name="crm"),
    path("empresas/", views.empresas, name="crm_empresas"),
    path("contatos/", views.contatos, name="crm_contatos"),
    path("funis/", views.funis, name="crm_funis"),
    path("funis/<int:pk>/", views.funil_detalhe, name="crm_funil_detalhe"),
    path("funis/<int:pk>/mover/", views.funil_mover_card, name="crm_funil_mover"),
    path("listas/", views.listas, name="crm_listas"),
]
