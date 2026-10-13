from django.http import HttpRequest

from .models import Funcionario


def obter_funcionario(request: HttpRequest) -> Funcionario | None:
    if not request.user.is_authenticated:
        return None
    return (
        Funcionario.objects.filter(usuario=request.user, ativo=True)
        .select_related("responde_a")
        .first()
    )
