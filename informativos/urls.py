from django.urls import path

from . import views

urlpatterns = [
    path("", views.lista, name="informativos"),
    path("<int:pk>/", views.detalhe, name="informativo_detalhe"),
    path("<int:pk>/editar/", views.editar, name="informativo_editar"),
    path("<int:pk>/deletar/", views.deletar, name="informativo_deletar"),
]
