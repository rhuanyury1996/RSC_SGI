from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Pagamento, StatusPagamento


@login_required
def lista(request):
    itens = Pagamento.objects.select_related("funcionario")
    status = request.GET.get("status")
    if status in StatusPagamento.values:
        itens = itens.filter(status=status)
    return render(
        request,
        "pagamentos/lista.html",
        {"itens": itens, "status_atual": status, "status_opcoes": StatusPagamento},
    )
