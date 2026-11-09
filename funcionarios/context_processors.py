from .acessos import EDITAR, NENHUM, eh_ceo, niveis_do_usuario
from .utils import obter_funcionario


def colaborador(request):
    funcionario = obter_funcionario(request)
    niveis = niveis_do_usuario(request.user, funcionario) if request.user.is_authenticated else {}
    return {
        "colaborador": funcionario,
        "eh_ceo": eh_ceo(request.user),
        # pode_ver.comercial / pode_editar.comercial nos templates
        "pode_ver": {m: n != NENHUM for m, n in niveis.items()},
        "pode_editar": {m: n == EDITAR for m, n in niveis.items()},
    }
