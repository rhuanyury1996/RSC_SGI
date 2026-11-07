"""Controle de acesso por módulo do SGI.

Cada funcionário tem um nível por módulo: editar, ver (só leitura) ou nenhum.
Superusuário sempre tem acesso total.
"""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

EDITAR = "editar"
VER = "ver"
NENHUM = "nenhum"

# (chave, rótulo, prefixo de URL)
MODULOS = (
    ("comercial", "Comercial (CRM)", "/comercial/"),
    ("orcamentos", "Orçamentos", "/orcamentos/"),
    ("atividades", "Atividades", "/atividades/"),
    ("apontamentos", "Apontamentos", "/apontamentos/"),
    ("calendario", "Calendário", "/calendario/"),
    ("informativos", "Informativos", "/informativos/"),
    ("pagamentos", "Pagamentos", "/pagamentos/"),
)
CAMPOS_ACESSO = tuple(f"acesso_{chave}" for chave, _r, _p in MODULOS)
METODOS_LEITURA = {"GET", "HEAD", "OPTIONS"}


def niveis_do_usuario(user, funcionario=None) -> dict:
    """{modulo: nivel}. Sem funcionário vinculado ou superusuário: tudo liberado."""
    total = {chave: EDITAR for chave, _r, _p in MODULOS}
    if not getattr(user, "is_authenticated", False) or user.is_superuser:
        return total
    if funcionario is None:
        from .models import Funcionario

        funcionario = Funcionario.objects.filter(usuario=user, ativo=True).first()
    if funcionario is None:
        return total
    return {
        chave: getattr(funcionario, f"acesso_{chave}", EDITAR) or EDITAR
        for chave, _r, _p in MODULOS
    }


def modulo_da_url(path: str) -> str | None:
    for chave, _r, prefixo in MODULOS:
        if path.startswith(prefixo):
            return chave
    return None


def _quer_json(request) -> bool:
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )


class AcessoModuloMiddleware:
    """Bloqueia módulo sem acesso e escrita em módulo só leitura."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        modulo = modulo_da_url(request.path)
        if modulo and user is not None and user.is_authenticated and not user.is_superuser:
            nivel = niveis_do_usuario(user).get(modulo, EDITAR)
            rotulo = dict((c, r) for c, r, _p in MODULOS)[modulo]
            if nivel == NENHUM:
                return self._negar(request, f"Você não tem acesso ao módulo {rotulo}.", ir_para_home=True)
            if nivel == VER and request.method not in METODOS_LEITURA:
                return self._negar(request, f"Seu acesso a {rotulo} é só leitura.")
        return self.get_response(request)

    @staticmethod
    def _negar(request, texto: str, ir_para_home: bool = False):
        if _quer_json(request):
            return JsonResponse({"ok": False, "erro": texto}, status=403)
        messages.error(request, texto)
        if ir_para_home:
            return redirect("home")
        destino = request.headers.get("referer") or ""
        if not url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            destino = "home"
        return redirect(destino)
