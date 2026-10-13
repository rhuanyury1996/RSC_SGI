from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from apontamentos.permissions import pode_aprovar_edicoes_marcacao
from funcionarios.utils import obter_funcionario

from .forms import InformativoForm
from .models import CategoriaInformativo, Informativo


def _pode_editar(user, item: Informativo) -> bool:
    if pode_aprovar_edicoes_marcacao(user):
        return True
    return bool(item.autor_id and item.autor_id == user.id)


@login_required
def lista(request):
    categoria = request.GET.get("categoria", "").strip()
    itens = (
        Informativo.objects.filter(ativo=True)
        .select_related("autor", "autor__funcionario")
        .order_by("-publicado_em")
    )
    if categoria in CategoriaInformativo.values:
        itens = itens.filter(categoria=categoria)
    else:
        categoria = ""

    if request.method == "POST":
        form = InformativoForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.autor = request.user
            post.ativo = True
            post.save()
            messages.success(request, "Informativo publicado.")
            return redirect("informativos")
    else:
        form = InformativoForm(initial={"categoria": CategoriaInformativo.NOVIDADES})

    pode_deletar = pode_aprovar_edicoes_marcacao(request.user)
    feed = [
        {
            "item": item,
            "pode_editar": _pode_editar(request.user, item),
            "pode_deletar": pode_deletar,
        }
        for item in itens[:80]
    ]

    return render(
        request,
        "informativos/lista.html",
        {
            "feed": feed,
            "form": form,
            "categorias": CategoriaInformativo,
            "categoria_atual": categoria,
            "funcionario": obter_funcionario(request),
            "pode_deletar_qualquer": pode_deletar,
        },
    )


@login_required
def detalhe(request, pk: int):
    item = get_object_or_404(
        Informativo.objects.select_related("autor", "autor__funcionario"),
        pk=pk,
        ativo=True,
    )
    return render(
        request,
        "informativos/detalhe.html",
        {
            "item": item,
            "pode_editar": _pode_editar(request.user, item),
            "pode_deletar": pode_aprovar_edicoes_marcacao(request.user),
        },
    )


@login_required
def editar(request, pk: int):
    item = get_object_or_404(Informativo, pk=pk, ativo=True)
    if not _pode_editar(request.user, item):
        messages.error(request, "Você só pode editar os seus próprios informativos.")
        return redirect("informativo_detalhe", pk=pk)

    if request.method == "POST":
        form = InformativoForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Informativo atualizado.")
            return redirect("informativo_detalhe", pk=item.pk)
    else:
        form = InformativoForm(instance=item)

    return render(
        request,
        "informativos/editar.html",
        {"form": form, "item": item},
    )


@login_required
def deletar(request, pk: int):
    if not pode_aprovar_edicoes_marcacao(request.user):
        messages.error(request, "Somente o Rhuan pode excluir informativos.")
        return redirect("informativos")

    item = get_object_or_404(Informativo, pk=pk, ativo=True)
    if request.method != "POST":
        return redirect("informativo_detalhe", pk=pk)

    item.delete()
    messages.success(request, "Informativo excluído.")
    return redirect("informativos")
