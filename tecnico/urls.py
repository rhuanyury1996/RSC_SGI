from django.urls import path

from . import views

urlpatterns = [
    path("", views.estudos, name="tecnico"),
    path("classificacao/novo/", views.novo, name="tecnico_estudo_novo"),
    path("classificacao/<int:pk>/", views.abrir, name="tecnico_estudo"),
    path("classificacao/<int:pk>/app/", views.calculadora, name="tecnico_estudo_app"),
    path("classificacao/<int:pk>/salvar/", views.salvar, name="tecnico_estudo_salvar"),
    path("classificacao/<int:pk>/dados/", views.dados, name="tecnico_estudo_dados"),
    path("classificacao/<int:pk>/duplicar/", views.duplicar, name="tecnico_estudo_duplicar"),
    path("classificacao/<int:pk>/status/", views.mudar_status, name="tecnico_estudo_status"),
]
