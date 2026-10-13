from django.urls import path

from . import views

urlpatterns = [
    path("", views.apontamentos, name="apontamentos"),
    path(
        "marcacoes/<int:pk>/editar/",
        views.solicitar_edicao_marcacao,
        name="solicitar_edicao_marcacao",
    ),
    path(
        "marcacoes/<int:pk>/excluir/",
        views.solicitar_exclusao_marcacao,
        name="solicitar_exclusao_marcacao",
    ),
    path(
        "edicoes/<int:pk>/revisar/",
        views.revisar_edicao_marcacao,
        name="revisar_edicao_marcacao",
    ),
    path("ferias/", views.ferias, name="ferias"),
    path("day-off/", views.day_off, name="day_off"),
    path("resumo/", views.resumo_horas, name="resumo_horas"),
]
