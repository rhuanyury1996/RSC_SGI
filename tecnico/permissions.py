"""Regras do Setor Técnico além do controle por módulo (funcionarios/acessos.py)."""
from funcionarios.acessos import EDITAR, niveis_do_usuario


def pode_editar_tecnico(request) -> bool:
    """Nível "editar" no módulo Setor Técnico (superusuário e CEO sempre podem)."""
    user = request.user
    if not user.is_authenticated:
        return False
    return niveis_do_usuario(user).get("tecnico", EDITAR) == EDITAR
