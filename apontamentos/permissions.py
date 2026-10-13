import os

from django.contrib.auth.models import AbstractBaseUser


def username_aprovador_marcacoes() -> str:
    return os.getenv("CEO_USERNAME", "rfloriano")


def pode_aprovar_edicoes_marcacao(user: AbstractBaseUser | None) -> bool:
    """Rhuan (CEO) ou superusuário pode aprovar correções de ponto."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    ceo = username_aprovador_marcacoes().lower()
    return (user.username or "").lower() == ceo
