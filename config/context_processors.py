from django.urls import reverse
from django.utils import timezone

from funcionarios.utils import obter_funcionario


def topbar(request):
    """Dados globais da topbar: informativos, produtividade e timer ativo."""
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
    timer = None
    funcionario = obter_funcionario(request)
    if funcionario is not None:
        from atividades.models import AtividadeDiaria, StatusAtividade
        from atividades.services import formatar_tempo, metricas_planner, q_aparece_no_dia

        from django.db.models import Q

        hoje = timezone.localdate()
        minhas = Q(responsavel=funcionario) | Q(participantes=funcionario)
        itens = list(
            AtividadeDiaria.objects.ativas()
            .filter(minhas)
            .filter(q_aparece_no_dia(hoje))
            .filter(atividade_pai__isnull=True)
            .distinct()
            .order_by("ordem", "hora_inicio", "pk")
        )
        metricas = metricas_planner(funcionario, hoje, itens)
        produtividade = {
            "percentual": metricas["percentual"],
            "feitos": metricas["feitos"],
            "total": metricas["total"],
            "focus_time": metricas["focus_time"],
            "focus_score": metricas["focus_score"],
        }

        ativo = next((a for a in itens if a.cronometro_ativo), None)
        if ativo is None:
            ativo = (
                AtividadeDiaria.objects.ativas()
                .filter(
                    minhas,
                    cronometro_inicio__isnull=False,
                )
                .distinct()
                .order_by("-cronometro_inicio")
                .first()
            )

        lista_href = (
            f"{reverse('atividades')}?org=status&data={hoje.isoformat()}"
        )
        if ativo is not None:
            segundos = ativo.tempo_atual_segundos()
            acumulado = int(ativo.tempo_acumulado_segundos or 0)
            timer = {
                "pk": ativo.pk,
                "titulo": ativo.titulo,
                "ativo": True,
                "segundos": segundos,
                "acumulado": acumulado,
                "texto": formatar_tempo(segundos),
                "inicio": ativo.cronometro_inicio.isoformat()
                if ativo.cronometro_inicio
                else "",
                "href": lista_href,
            }
        else:
            sugestao = next(
                (
                    a
                    for a in itens
                    if a.status
                    in (
                        StatusAtividade.EXECUTANDO,
                        StatusAtividade.NAO_INICIADO,
                        StatusAtividade.EM_REVISAO,
                    )
                ),
                None,
            )
            if sugestao is not None:
                segundos = sugestao.tempo_atual_segundos()
                timer = {
                    "pk": sugestao.pk,
                    "titulo": sugestao.titulo,
                    "ativo": False,
                    "segundos": segundos,
                    "acumulado": int(sugestao.tempo_acumulado_segundos or 0),
                    "texto": formatar_tempo(segundos),
                    "inicio": "",
                    "href": lista_href,
                }

    return {
        "topbar_informativos": informativos,
        "topbar_informativos_count": len(informativos),
        "topbar_produtividade": produtividade,
        "topbar_timer": timer,
    }
