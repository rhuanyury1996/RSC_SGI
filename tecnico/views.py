"""Telas do Setor Técnico: estudos de classificação de áreas.

A calculadora é uma página própria (templates/tecnico/calculadora.html), aberta
dentro de um iframe na tela do estudo. Ela recebe o estado em
<script id="sgi-ca" type="application/json"> e grava de volta por POST JSON
em `salvar`. O acesso ao módulo é controlado pelo AcessoModuloMiddleware
(prefixo /tecnico/): "só ver" bloqueia o POST de salvar com 403.
"""
from __future__ import annotations

import copy
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from funcionarios.utils import obter_funcionario

from .models import EstudoClassificacao, StatusEstudo
from .permissions import pode_editar_tecnico

LIMITE_ESTADO_BYTES = 5 * 1024 * 1024  # 5 MB


@login_required
def estudos(request):
    qs = EstudoClassificacao.objects.select_related("atualizado_por", "empresa")
    filtro = {"q": request.GET.get("q", "").strip(), "status": request.GET.get("status", "")}
    if filtro["q"]:
        qs = qs.filter(nome__icontains=filtro["q"]) | qs.filter(cliente__icontains=filtro["q"])
    if filtro["status"]:
        qs = qs.filter(status=filtro["status"])
    elif not request.GET.get("arquivados"):
        qs = qs.exclude(status=StatusEstudo.ARQUIVADO)
    return render(
        request,
        "tecnico/estudos.html",
        {
            "estudos": qs.order_by("-atualizado_em"),
            "filtro": filtro,
            "status_opcoes": StatusEstudo.choices,
            "pode_editar": pode_editar_tecnico(request),
        },
    )


@login_required
@require_POST
def novo(request):
    nome = (request.POST.get("nome") or "").strip()
    if not nome:
        messages.error(request, "Informe o nome do projeto.")
        return redirect("tecnico")
    funcionario = obter_funcionario(request)
    estudo = EstudoClassificacao.objects.create(
        nome=nome,
        cliente=(request.POST.get("cliente") or "").strip(),
        criado_por=funcionario,
        atualizado_por=funcionario,
    )
    messages.success(request, f"Estudo {estudo.nome} criado.")
    return redirect("tecnico_estudo", pk=estudo.pk)


@login_required
def abrir(request, pk: int):
    estudo = get_object_or_404(EstudoClassificacao, pk=pk)
    return render(
        request,
        "tecnico/estudo.html",
        {"estudo": estudo, "status_opcoes": StatusEstudo.choices, "pode_editar": pode_editar_tecnico(request)},
    )


@login_required
@xframe_options_sameorigin
def calculadora(request, pk: int):
    """Página da calculadora (vai dentro do iframe da tela do estudo)."""
    estudo = get_object_or_404(EstudoClassificacao, pk=pk)
    funcionario = obter_funcionario(request)
    config = {
        "id": estudo.pk,
        "nome": estudo.nome,
        "cliente": estudo.cliente,
        "revisao": estudo.revisao,
        "autor": funcionario.nome_completo if funcionario else (request.user.get_full_name() or request.user.username),
        "estado": estudo.estado or {},
        "salvar_url": reverse("tecnico_estudo_salvar", args=[estudo.pk]),
        "csrf": get_token(request),
        "somente_leitura": not pode_editar_tecnico(request),
    }
    return render(request, "tecnico/calculadora.html", {"config": config})


@login_required
def salvar(request, pk: int):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not pode_editar_tecnico(request):
        return JsonResponse({"ok": False, "erro": "Seu acesso ao Setor Técnico é só leitura."}, status=403)
    estudo = get_object_or_404(EstudoClassificacao, pk=pk)
    if len(request.body) > LIMITE_ESTADO_BYTES:
        return JsonResponse({"ok": False, "erro": "Estudo grande demais para salvar (limite de 5 MB)."}, status=413)
    try:
        estado = json.loads(request.body or b"{}").get("estado")
    except (ValueError, AttributeError):
        return JsonResponse({"ok": False, "erro": "JSON inválido."}, status=400)
    if not isinstance(estado, dict) or estado.get("v") != 1 or not isinstance(estado.get("fontes"), list):
        return JsonResponse({"ok": False, "erro": "Estado da calculadora em formato inesperado."}, status=400)

    estudo.estado = estado
    cab = estado.get("estudo") or {}
    if (cab.get("projeto") or "").strip():
        estudo.nome = cab["projeto"].strip()[:200]
    if (cab.get("cliente") or "").strip():
        estudo.cliente = cab["cliente"].strip()[:200]
    if (cab.get("rev") or "").strip():
        estudo.revisao = str(cab["rev"]).strip()[:10]
    estudo.atualizado_por = obter_funcionario(request)
    estudo.save()
    return JsonResponse({"ok": True, "atualizado_em": estudo.atualizado_em.isoformat()})


@login_required
def dados(request, pk: int):
    """Estado do estudo em JSON (backup e integração)."""
    estudo = get_object_or_404(EstudoClassificacao, pk=pk)
    resp = JsonResponse(estudo.estado or {}, json_dumps_params={"ensure_ascii": False, "indent": 1})
    resp["Content-Disposition"] = f'attachment; filename="estudo_{estudo.pk}_rev{estudo.revisao}.json"'
    return resp


@login_required
@require_POST
def duplicar(request, pk: int):
    if not pode_editar_tecnico(request):
        messages.error(request, "Seu acesso ao Setor Técnico é só leitura.")
        return redirect("tecnico")
    orig = get_object_or_404(EstudoClassificacao, pk=pk)
    funcionario = obter_funcionario(request)
    novo_estudo = EstudoClassificacao.objects.create(
        nome=f"{orig.nome} (cópia)",
        cliente=orig.cliente,
        empresa=orig.empresa,
        revisao=orig.revisao,
        estado=copy.deepcopy(orig.estado),
        criado_por=funcionario,
        atualizado_por=funcionario,
    )
    messages.success(request, "Estudo duplicado.")
    return redirect("tecnico_estudo", pk=novo_estudo.pk)


@login_required
@require_POST
def mudar_status(request, pk: int):
    estudo = get_object_or_404(EstudoClassificacao, pk=pk)
    status = request.POST.get("status")
    if status in StatusEstudo.values:
        estudo.status = status
        estudo.atualizado_por = obter_funcionario(request)
        estudo.save(update_fields=["status", "atualizado_por", "atualizado_em"])
        messages.success(request, f"Status alterado para {estudo.get_status_display()}.")
    voltar = request.POST.get("voltar") or ""
    if voltar and url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(voltar)
    return redirect("tecnico")
