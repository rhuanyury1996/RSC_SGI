from django.utils import timezone

from funcionarios.utils import obter_funcionario


def topbar(request):
    """Dados globais da topbar: informativos recentes + produtividade do dia."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    from informativos.models import Informativo

    informativos = list(
        Informativo.objects.filter(ativo=True)
        .only("id", "titulo", "categoria", "publicado_em", "conteudo")
        .order_by("-publicado_em")[:6]
    )

    produtividade = {
        "percentual": 0,
        "feitos": 0,
        "total": 0,
        "focus_time": "00:00",
    }
    funcionario = obter_funcionario(request)
    if funcionario is not None:
        from atividades.models import AtividadeDiaria
        from atividades.services import formatar_tempo, metricas_planner

        hoje = timezone.localdate()
        itens = list(
            AtividadeDiaria.objects.filter(
                responsavel=funcionario,
                planejado_para=hoje,
            )
        )
        metricas = metricas_planner(funcionario, hoje, itens)
        produtividade = {
            "percentual": metricas["percentual"],
            "feitos": metricas["feitos"],
            "total": metricas["total"],
            "focus_time": metricas["focus_time"],
            "focus_score": metricas["focus_score"],
        }

    return {
        "topbar_informativos": informativos,
        "topbar_informativos_count": len(informativos),
        "topbar_produtividade": produtividade,
    }
