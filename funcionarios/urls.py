from django.urls import path

from .views import (
    AcessoLoginView,
    alterar_senha,
    editar_perfil,
    home,
    logout_view,
    meu_perfil,
    organograma,
)

urlpatterns = [
    path("", home, name="home"),
    path("login/", AcessoLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("perfil/", meu_perfil, name="meu_perfil"),
    path("perfil/editar/", editar_perfil, name="editar_perfil"),
    path("perfil/senha/", alterar_senha, name="alterar_senha"),
    path("organograma/", organograma, name="organograma"),
]
