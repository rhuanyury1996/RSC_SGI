from django.urls import path

from . import views

urlpatterns = [
    path("", views.calendario, name="calendario"),
    path("demandas/", views.demandas, name="demandas"),
    path("demandas/<int:pk>/status/", views.demanda_status, name="demanda_status"),
    path("google/conectar/", views.google_conectar, name="google_calendar_conectar"),
    path("google/callback/", views.google_callback, name="google_calendar_callback"),
    path("google/desconectar/", views.google_desconectar, name="google_calendar_desconectar"),
]
