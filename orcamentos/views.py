"""Telas do módulo de orçamento GEXCON."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from crm.models import Empresa
from funcionarios.utils import obter_funcionario

from . import services
from .forms import OrcamentoForm, TabelaParametrosForm
from .models import Escopo, Orcamento, StatusOrcamento, TabelaParametros
from .permissions import pode_gerir_parametros, pode_sobrescrever_sequencial

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@login_required
def novo(request):
    """Formulário → pré-visualização dos valores → emitir a proposta."""
    funcionario = obter_funcionario(request)
    admin = pode_sobrescrever_sequencial(funcionario)
    previa = None
    pendencias = []

    if request.method == "POST":
        form = OrcamentoForm(request.POST, pode_sobrescrever_sequencial=admin)
        if form.is_valid():
            dados = form.dados_do_pedido()
            pendencias = services.pendencias_cadastro(dados["empresa"])
            try:
                if request.POST.get("acao") == "emitir":
                    orc = services.emitir(dados, funcionario)
                    messages.success(request, f"Proposta {orc.numero} emitida.")
                    return redirect("orcamentos")
                calculado, _params, _tabela = services.calcular(dados)
                previa = services.resumo_valores(calculado)
            except services.OrcamentoErro as exc:
                messages.error(request, str(exc))
    else:
        form = OrcamentoForm(pode_sobrescrever_sequencial=admin)

    return render(
        request,
        "orcamentos/novo.html",
        {
            "form": form,
            "previa": previa,
            "pendencias": pendencias,
            "contatos_por_empresa": json.dumps(_contatos_por_empresa()),
            "pode_admin": admin,
            "funcionario": funcionario,
        },
    )


def _contatos_por_empresa() -> dict[str, list[dict]]:
    """Mapa empresa → contatos, para o select de contato filtrar sem ida ao servidor."""
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
def historico(request):
    """Listagem das propostas emitidas, com filtros e download."""
    itens = Orcamento.objects.select_related("empresa", "emitido_por").defer("arquivo")

    empresa = request.GET.get("empresa", "").strip()
    escopo = request.GET.get("escopo", "").strip()
    status = request.GET.get("status", "").strip()
    de = request.GET.get("de", "").strip()
    ate = request.GET.get("ate", "").strip()

    if empresa:
        itens = itens.filter(empresa_id=empresa)
    if escopo in Escopo.values:
        itens = itens.filter(escopo=escopo)
    else:
        escopo = ""
    if status in StatusOrcamento.values:
        itens = itens.filter(status=status)
    else:
        status = ""
    if de:
        itens = itens.filter(data__gte=de)
    if ate:
        itens = itens.filter(data__lte=ate)

    return render(
        request,
        "orcamentos/historico.html",
        {
            "itens": itens[:300],
            "empresas": Empresa.objects.filter(orcamentos__isnull=False).distinct().order_by("nome"),
            "escopos": Escopo.choices,
            "status_opcoes": StatusOrcamento.choices,
            "filtro": {"empresa": empresa, "escopo": escopo, "status": status, "de": de, "ate": ate},
            "funcionario": obter_funcionario(request),
        },
    )


@login_required
def download(request, pk: int):
    orc = get_object_or_404(Orcamento, pk=pk)
    resposta = HttpResponse(bytes(orc.arquivo), content_type=DOCX_MIME)
    resposta["Content-Disposition"] = f'attachment; filename="{orc.nome_arquivo}"'
    return resposta


@login_required
def mudar_status(request, pk: int):
    orc = get_object_or_404(Orcamento, pk=pk)
    status = request.POST.get("status", "")
    if request.method != "POST" or status not in StatusOrcamento.values:
        messages.error(request, "Status inválido.")
    else:
        services.mudar_status(orc, status, obter_funcionario(request))
        messages.success(request, f"Proposta {orc.numero}: {orc.get_status_display().lower()}.")
    return redirect("orcamentos")


@login_required
def parametros(request):
    """Tabelas de preço por ano. Só gestores editam."""
    funcionario = obter_funcionario(request)
    pode_editar = pode_gerir_parametros(funcionario)
    form = None

    if pode_editar:
        if request.method == "POST":
            form = TabelaParametrosForm(request.POST)
            if form.is_valid():
                tabela = form.save(commit=False)
                tabela.atualizado_por = funcionario
                tabela.save()
                messages.success(request, f"Tabela de {tabela.ano} salva.")
                return redirect("orcamento_parametros")
        else:
            form = TabelaParametrosForm(initial={"ano": timezone.localdate().year + 1})

    return render(
        request,
        "orcamentos/parametros.html",
        {
            "tabelas": TabelaParametros.objects.select_related("atualizado_por"),
            "form": form,
            "pode_editar": pode_editar,
            "funcionario": funcionario,
        },
    )


@login_required
def parametros_editar(request, ano: int):
    funcionario = obter_funcionario(request)
    if not pode_gerir_parametros(funcionario):
        messages.error(request, "Só gestores editam a tabela de parâmetros.")
        return redirect("orcamento_parametros")

    tabela = get_object_or_404(TabelaParametros, ano=ano)
    if request.method == "POST":
        form = TabelaParametrosForm(request.POST, instance=tabela)
        if form.is_valid():
            tabela = form.save(commit=False)
            tabela.atualizado_por = funcionario
            tabela.save()
            messages.success(request, f"Tabela de {tabela.ano} atualizada.")
            return redirect("orcamento_parametros")
    else:
        form = TabelaParametrosForm(instance=tabela)

    return render(
        request,
        "orcamentos/parametros_editar.html",
        {"form": form, "tabela": tabela, "funcionario": funcionario},
    )


@login_required
def contatos_json(request, empresa_id: int):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    return JsonResponse({"contatos": _contatos_por_empresa().get(str(empresa.pk), [])})
