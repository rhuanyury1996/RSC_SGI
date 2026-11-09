"""Financeiro: só o CEO (rfloriano) acessa. Para os outros a área nem existe (404)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import Http404

from funcionarios.acessos import eh_ceo

SLUG_ESPACO = "rsc"


def espaco_do_ceo(user):
    """Espaço financeiro único do SGI (cria e semeia na primeira vez)."""
    from ledger.seed import seed_clients, seed_employees, seed_workspace
    from workspaces.models import Membership, Workspace

    espaco, criado = Workspace.objects.get_or_create(
        slug=SLUG_ESPACO, defaults={"name": "RSC", "owner": user}
    )
    Membership.objects.get_or_create(
        workspace=espaco, user=user, defaults={"role": Membership.Role.OWNER}
    )
    if criado:
        seed_workspace(espaco)
    seed_clients(espaco)
    seed_employees(espaco)
    return espaco


def somente_ceo(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not eh_ceo(request.user):
            raise Http404()
        request.workspace = espaco_do_ceo(request.user)
        return view(request, *args, **kwargs)

    return wrapper
