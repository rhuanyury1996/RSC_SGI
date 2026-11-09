from django.urls import path
from django.views.generic import RedirectView

# Pagamentos virou Financeiro (acesso só do CEO, travado no middleware)
urlpatterns = [
    path("", RedirectView.as_view(pattern_name="financeiro:painel"), name="pagamentos"),
]
