"""Financeiro: o CEO (rfloriano) sempre acessa; os demais só com acesso liberado
no admin (Acessos aos módulos > Financeiro). Sem acesso, a área nem existe (404)."""
import os
from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404

from funcionarios.acessos import NENHUM, eh_ceo, niveis_do_usuario

SLUG_ESPACO = "rsc"


def pode_acessar_financeiro(user) -> bool:
    return niveis_do_usuario(user).get("financeiro", NENHUM) != NENHUM


def _dono_do_espaco(user):
    """O espaço é sempre do CEO; se ele ainda não existir no banco, de quem abriu."""
    if eh_ceo(user):
        return user
    ceo = os.getenv("CEO_USERNAME", "rfloriano")
    return get_user_model().objects.filter(username__iexact=ceo).first() or user


def espaco_do_ceo(user):
    """Espaço financeiro único do SGI (cria e semeia na primeira vez)."""
    from ledger.seed import seed_clients, seed_employees, seed_workspace
    from workspaces.models import Membership, Workspace

    espaco, criado = Workspace.objects.get_or_create(
        slug=SLUG_ESPACO, defaults={"name": "RSC", "owner": _dono_do_espaco(user)}
    )
    papel = Membership.Role.OWNER if eh_ceo(user) else Membership.Role.MEMBER
    Membership.objects.get_or_create(workspace=espaco, user=user, defaults={"role": papel})
    if criado:
        seed_workspace(espaco)
    seed_clients(espaco)
    seed_employees(espaco)
    return espaco


def somente_ceo(view):
    """Libera o CEO e quem tem acesso ao Financeiro. "Só ver" é barrado no middleware."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not pode_acessar_financeiro(request.user):
            raise Http404()
        request.workspace = espaco_do_ceo(request.user)
        return view(request, *args, **kwargs)

    return wrapper
