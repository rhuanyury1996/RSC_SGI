"""Telas do orçamento RAVEN (mesmo fluxo do GEXCON: novo → prévia → emitir → histórico)."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from crm.models import Empresa
from funcionarios.utils import obter_funcionario

from . import services
from .forms import OrcamentoRavenForm, TabelaRavenForm
from .models import OrcamentoRaven, StatusOrcamento, TabelaRaven, TipoClienteRaven
from orcamentos.permissions import pode_gerir_parametros, pode_sobrescrever_sequencial


def _contatos_por_empresa() -> dict[str, list[dict]]:
    """Mapa empresa → contatos ativos, para o select de contato filtrar sem ida ao servidor."""
    mapa: dict[str, list[dict]] = {}
    for empresa in Empresa.objects.filter(ativa=True).prefetch_related("contatos"):
        itens = [
            {"id": c.pk, "nome": c.nome_completo, "principal": c.principal}
            for c in empresa.contatos.all()
            if c.ativo
        ]
        itens.sort(key=lambda c: (not c["principal"], c["nome"]))
        mapa[str(empresa.pk)] = itens
    return mapa


@login_required
def novo(request):
    funcionario = obter_funcionario(request)
    admin = pode_sobrescrever_sequencial(funcionario)
    previa = None
    pendencias = []
    if request.method == "POST":
        form = OrcamentoRavenForm(request.POST, pode_sobrescrever_sequencial=admin)
        if form.is_valid():
            dados = form.dados_do_pedido()
            pendencias = services.pendencias_cadastro(dados["empresa"])
            try:
                if request.POST.get("acao") == "emitir":
                    orc = services.emitir(dados, funcionario)
                    messages.success(request, f"Proposta RAVEN {orc.numero} emitida.")
                    return redirect("orcamentos_raven")
                res, _tabela = services.calcular(dados)
                previa = services.resumo_valores(res)
            except services.OrcamentoErro as exc:
                messages.error(request, str(exc))
    else:
        form = OrcamentoRavenForm(pode_sobrescrever_sequencial=admin)
    return render(
        request,
        "orcamentos_raven/novo.html",
        {
            "form": form,
            "previa": previa,
            "pendencias": pendencias,
            "contatos_por_empresa": json.dumps(_contatos_por_empresa()),
            "pode_admin": admin,
            "funcionario": funcionario,
        },
    )


@login_required
def historico(request):
    itens = OrcamentoRaven.objects.select_related("empresa", "emitido_por", "tabela").defer("arquivo")
    empresa = request.GET.get("empresa", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    status = request.GET.get("status", "").strip()
    de = request.GET.get("de", "").strip()
    ate = request.GET.get("ate", "").strip()
    if empresa:
        itens = itens.filter(empresa_id=empresa)
    if tipo in TipoClienteRaven.values:
        itens = itens.filter(tipo_cliente=tipo)
    else:
        tipo = ""
    if status == "login":
        itens = itens.filter(status=StatusOrcamento.ACEITA, login_liberado_em__isnull=True)
    elif status in StatusOrcamento.values:
        itens = itens.filter(status=status)
    else:
        status = ""
    if de:
        itens = itens.filter(data__gte=de)
    if ate:
        itens = itens.filter(data__lte=ate)
    pendentes_login = OrcamentoRaven.objects.filter(status=StatusOrcamento.ACEITA, login_liberado_em__isnull=True).count()
    return render(
        request,
        "orcamentos_raven/historico.html",
        {
            "itens": itens[:300],
            "empresas": Empresa.objects.filter(orcamentos_raven__isnull=False).distinct().order_by("nome"),
            "tipos": TipoClienteRaven.choices,
            "status_opcoes": StatusOrcamento.choices,
            "filtro": {"empresa": empresa, "tipo": tipo, "status": status, "de": de, "ate": ate},
            "pendentes_login": pendentes_login,
            "agora": timezone.now(),
            "funcionario": obter_funcionario(request),
        },
    )


@login_required
def abrir(request, pk: int):
    """Abre a proposta no navegador (o cliente/usuário imprime ou salva em PDF)."""
    orc = get_object_or_404(OrcamentoRaven, pk=pk)
    return HttpResponse(bytes(orc.arquivo), content_type="text/html; charset=utf-8")


@login_required
def download(request, pk: int):
    orc = get_object_or_404(OrcamentoRaven, pk=pk)
    resposta = HttpResponse(bytes(orc.arquivo), content_type="text/html; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{orc.nome_arquivo}"'
    return resposta


@login_required
def mudar_status(request, pk: int):
    orc = get_object_or_404(OrcamentoRaven, pk=pk)
    status = request.POST.get("status", "")
    if request.method != "POST" or status not in StatusOrcamento.values:
        messages.error(request, "Status inválido.")
    else:
        services.mudar_status(orc, status, obter_funcionario(request))
        if status == StatusOrcamento.ACEITA and orc.prazo_login:
            messages.success(
                request,
                f"Proposta {orc.numero} aceita. Libere o login até {timezone.localtime(orc.prazo_login):%d/%m/%Y %H:%M}.",
            )
        else:
            messages.success(request, f"Proposta {orc.numero}: {orc.get_status_display().lower()}.")
    return redirect("orcamentos_raven")


@login_required
def liberar_login(request, pk: int):
    orc = get_object_or_404(OrcamentoRaven, pk=pk)
    if request.method != "POST":
        return redirect("orcamentos_raven")
    try:
        services.liberar_login(orc, obter_funcionario(request))
        messages.success(request, f"Login da proposta {orc.numero} marcado como liberado.")
    except services.OrcamentoErro as exc:
        messages.error(request, str(exc))
    return redirect("orcamentos_raven")


@login_required
def parametros(request):
    funcionario = obter_funcionario(request)
    pode_editar = pode_gerir_parametros(funcionario)
    form = None
    if pode_editar:
        if request.method == "POST":
            form = TabelaRavenForm(request.POST)
            if form.is_valid():
                tabela = form.save(commit=False)
                tabela.atualizado_por = funcionario
                tabela.save()
                messages.success(request, f"Tabela RAVEN de {tabela.ano} salva.")
                return redirect("orcamento_raven_parametros")
        else:
            form = TabelaRavenForm(initial={"ano": timezone.localdate().year + 1})
    return render(
        request,
        "orcamentos_raven/parametros.html",
        {
            "tabelas": TabelaRaven.objects.select_related("atualizado_por"),
            "form": form,
            "pode_editar": pode_editar,
            "funcionario": funcionario,
        },
    )


@login_required
def parametros_editar(request, ano: int):
    funcionario = obter_funcionario(request)
    if not pode_gerir_parametros(funcionario):
        messages.error(request, "Só gestores editam a tabela RAVEN.")
        return redirect("orcamento_raven_parametros")
    tabela = get_object_or_404(TabelaRaven, ano=ano)
    if request.method == "POST":
        form = TabelaRavenForm(request.POST, instance=tabela)
        if form.is_valid():
            tabela = form.save(commit=False)
            tabela.atualizado_por = funcionario
            tabela.save()
            messages.success(request, f"Tabela RAVEN de {tabela.ano} atualizada.")
            return redirect("orcamento_raven_parametros")
    else:
        form = TabelaRavenForm(instance=tabela)
    return render(
        request,
        "orcamentos_raven/parametros_editar.html",
        {"form": form, "tabela": tabela, "funcionario": funcionario},
    )
