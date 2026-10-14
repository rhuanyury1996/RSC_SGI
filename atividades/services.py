from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Case, Count, F, IntegerField, Q, QuerySet, When
from django.utils import timezone

from funcionarios.models import Funcionario

from .models import (
    COPOS_AGUA_META,
    HABITOS_PADRAO,
    ML_POR_COPO,
    STATUS_ORDEM,
    AtividadeDiaria,
    DiaPlanner,
    HabitoDia,
    MetaFoco,
    PrioridadeAtividade,
    QuadranteEisenhower,
    StatusAtividade,
    quadrante_por_prioridade,
)
from .permissions import pode_dirigir_atividades


def _prio_rank():
    return Case(
        When(prioridade=PrioridadeAtividade.URGENTE, then=0),
        When(prioridade=PrioridadeAtividade.ALTA, then=1),
        When(prioridade=PrioridadeAtividade.MEDIA, then=2),
        default=3,
        output_field=IntegerField(),
    )


def _q_membro(funcionario_id: int) -> Q:
    return (
        Q(responsavel_id=funcionario_id)
        | Q(participantes=funcionario_id)
        | Q(subtarefas__responsavel_id=funcionario_id)
        | Q(subtarefas__participantes=funcionario_id)
    )


def queryset_visivel(
    ator: Funcionario,
    *,
    escopo: str = "minhas",
    responsavel_id: int | None = None,
) -> QuerySet[AtividadeDiaria]:
    qs = (
        AtividadeDiaria.objects.select_related(
            "responsavel", "criado_por", "cliente_rsc", "atividade_pai"
        )
        .prefetch_related("participantes", "subtarefas__responsavel", "subtarefas__participantes")
    )
    if escopo == "equipe" and pode_dirigir_atividades(ator):
        if responsavel_id:
            qs = qs.filter(_q_membro(responsavel_id)).distinct()
        return qs
    return qs.filter(_q_membro(ator.pk)).distinct()


def atividades_filtradas(
    ator: Funcionario,
    *,
    escopo: str = "minhas",
    responsavel_id: int | None = None,
    dia: date | None = None,
    organizacao: str = "status",
) -> QuerySet[AtividadeDiaria]:
    qs = queryset_visivel(ator, escopo=escopo, responsavel_id=responsavel_id)
    # Lista e Planner compartilham o mesmo recorte do dia
    if dia is not None:
        qs = qs.filter(Q(planejado_para=dia) | Q(data_vencimento=dia))
    # Subtarefas ficam aninhadas no pai (prefetch); evita linha duplicada na lista
    qs = qs.filter(atividade_pai__isnull=True)
    return qs.annotate(prio_rank=_prio_rank()).order_by(
        F("hora_inicio").asc(nulls_last=True),
        "ordem",
        "prio_rank",
        "-criado_em",
        "-id",
    )


def agrupar_por_status(itens: QuerySet[AtividadeDiaria]) -> list[dict]:
    buckets: dict[str, list] = defaultdict(list)
    for item in itens:
        buckets[item.status].append(item)
    grupos = []
    for status in STATUS_ORDEM:
        grupos.append(
            {
                "status": status,
                "label": StatusAtividade(status).label,
                "itens": buckets.get(status, []),
                "count": len(buckets.get(status, [])),
            }
        )
    return grupos


def agrupar_por_prioridade(itens: QuerySet[AtividadeDiaria]) -> list[dict]:
    ordem = [
        PrioridadeAtividade.URGENTE,
        PrioridadeAtividade.ALTA,
        PrioridadeAtividade.MEDIA,
        PrioridadeAtividade.BAIXA,
    ]
    buckets: dict[str, list] = defaultdict(list)
    for item in itens:
        buckets[item.prioridade].append(item)
    return [
        {
            "status": p,
            "label": PrioridadeAtividade(p).label,
            "itens": buckets.get(p, []),
            "count": len(buckets.get(p, [])),
            "kind": "prioridade",
        }
        for p in ordem
    ]


def agrupar_por_pessoa(
    itens: QuerySet[AtividadeDiaria] | list[AtividadeDiaria],
    membros: list[Funcionario],
) -> list[dict]:
    """Quadro da equipe: seção por pessoa (inclui participação e subtarefas)."""
    buckets: dict[int, list] = defaultdict(list)
    responsaveis: dict[int, Funcionario] = {m.pk: m for m in membros}
    for item in itens:
        vistos: set[int] = set()
        for membro in item.membros_equipe():
            buckets[membro.pk].append(item)
            responsaveis[membro.pk] = membro
            vistos.add(membro.pk)
        for sub in item.subtarefas.all():
            for membro in sub.membros_equipe():
                if membro.pk in vistos:
                    continue
                buckets[membro.pk].append(item)
                responsaveis[membro.pk] = membro
                vistos.add(membro.pk)

    ordem_ids = [m.pk for m in membros]
    for pk in buckets:
        if pk not in ordem_ids:
            ordem_ids.append(pk)

    grupos = []
    for pk in ordem_ids:
        pessoa = responsaveis.get(pk)
        if pessoa is None:
            continue
        lista = buckets.get(pk, [])
        feitos = sum(1 for i in lista if i.status == StatusAtividade.REALIZADO)
        grupos.append(
            {
                "status": f"pessoa_{pk}",
                "label": pessoa.nome_completo,
                "pessoa": pessoa,
                "itens": lista,
                "count": len(lista),
                "realizados": feitos,
                "kind": "pessoa",
            }
        )
    return grupos


def definir_participantes(
    atividade: AtividadeDiaria,
    participantes,
) -> None:
    ids = []
    for p in participantes or []:
        pk = getattr(p, "pk", p)
        if pk and pk != atividade.responsavel_id:
            ids.append(pk)
    atividade.participantes.set(ids)


def montar_arvore_atividades(itens) -> list:
    """Raízes com .filhos anexados; subtarefas órfãs visíveis sobem como raiz."""
    lista = list(itens)
    by_id = {a.pk: a for a in lista}
    for a in lista:
        a.filhos = []
    raizes = []
    for a in lista:
        if a.atividade_pai_id and a.atividade_pai_id in by_id:
            by_id[a.atividade_pai_id].filhos.append(a)
        else:
            raizes.append(a)
    from datetime import time as time_cls

    # Anexa todas as subtarefas do prefetch (lista já exclui filhos no topo)
    for a in raizes:
        if hasattr(a, "_prefetched_objects_cache") and "subtarefas" in a._prefetched_objects_cache:
            vistos = {f.pk for f in a.filhos}
            for sub in a.subtarefas.all():
                if sub.pk not in vistos:
                    a.filhos.append(sub)
                    vistos.add(sub.pk)
        a.filhos.sort(
            key=lambda s: (
                s.hora_inicio is None,
                s.hora_inicio or time_cls.min,
                s.ordem,
                s.pk,
            )
        )
    return raizes


def criar_atividade(
    ator: Funcionario,
    *,
    titulo: str,
    responsavel: Funcionario | None = None,
    participantes=None,
    atividade_pai: AtividadeDiaria | None = None,
    status: str = StatusAtividade.NAO_INICIADO,
    prioridade: str = PrioridadeAtividade.MEDIA,
    descricao: str = "",
    cliente_rsc=None,
    planejado_para: date | None = None,
    data_vencimento: date | None = None,
    hora_inicio=None,
    hora_fim=None,
) -> AtividadeDiaria:
    from datetime import time as time_cls

    dest = responsavel or ator
    if not pode_dirigir_atividades(ator) and dest.pk != ator.pk:
        dest = ator
    dia = planejado_para or timezone.localdate()
    status = status or StatusAtividade.NAO_INICIADO
    # Novas tarefas ficam no topo do grupo (sem horário) ou na ordem do horário
    AtividadeDiaria.objects.filter(status=status).update(ordem=F("ordem") + 1)
    prio = prioridade or PrioridadeAtividade.MEDIA
    if isinstance(hora_inicio, str) and hora_inicio:
        hora_inicio = time_cls.fromisoformat(hora_inicio)
    if isinstance(hora_fim, str) and hora_fim:
        hora_fim = time_cls.fromisoformat(hora_fim)
    if atividade_pai is not None and cliente_rsc is None:
        cliente_rsc = atividade_pai.cliente_rsc
    if atividade_pai is not None and planejado_para is None:
        dia = atividade_pai.planejado_para or dia
    item = AtividadeDiaria(
        responsavel=dest,
        criado_por=ator,
        atividade_pai=atividade_pai,
        titulo=titulo.strip(),
        descricao=(descricao or "").strip(),
        cliente_rsc=cliente_rsc,
        status=status,
        prioridade=prio,
        quadrante=quadrante_por_prioridade(prio),
        ordem=0,
        planejado_para=dia,
        data_vencimento=data_vencimento,
        hora_inicio=hora_inicio or None,
        hora_fim=hora_fim or None,
    )
    item.sincronizar_conclusao()
    item.save()
    if participantes is not None:
        definir_participantes(item, participantes)
    return item


def atualizar_atividade(atividade: AtividadeDiaria, **campos) -> AtividadeDiaria:
    participantes = campos.pop("participantes", None)
    for key, value in campos.items():
        if value is not None or key in (
            "descricao",
            "cliente_rsc",
            "data_vencimento",
            "planejado_para",
            "hora_inicio",
            "hora_fim",
            "quadrante",
        ):
            setattr(atividade, key, value)
    if "titulo" in campos and campos["titulo"] is not None:
        atividade.titulo = str(campos["titulo"]).strip()
    if "descricao" in campos:
        atividade.descricao = (campos.get("descricao") or "").strip()
    atividade.sincronizar_conclusao()
    atividade.save()
    if participantes is not None:
        definir_participantes(atividade, participantes)
    return atividade


def alterar_status(atividade: AtividadeDiaria, status: str) -> AtividadeDiaria:
    if status not in StatusAtividade.values:
        return atividade
    if status == StatusAtividade.REALIZADO and atividade.cronometro_inicio:
        parar_cronometro(atividade)
        atividade.refresh_from_db()
    atividade.status = status
    atividade.sincronizar_conclusao()
    atividade.save(
        update_fields=["status", "concluida", "concluida_em", "atualizado_em"]
    )
    return atividade


def excluir_atividade(atividade: AtividadeDiaria) -> None:
    atividade.delete()


def iniciar_cronometro(atividade: AtividadeDiaria, ator: Funcionario) -> AtividadeDiaria:
    # Um cronômetro ativo por pessoa (em qualquer tarefa da equipe)
    ativos = (
        AtividadeDiaria.objects.filter(cronometro_inicio__isnull=False)
        .filter(Q(responsavel=ator) | Q(participantes=ator))
        .exclude(pk=atividade.pk)
        .distinct()
    )
    for outro in ativos:
        parar_cronometro(outro)

    if atividade.cronometro_inicio:
        return atividade

    if atividade.status == StatusAtividade.NAO_INICIADO:
        atividade.status = StatusAtividade.EXECUTANDO
        atividade.sincronizar_conclusao()

    atividade.cronometro_inicio = timezone.now()
    atividade.save(
        update_fields=[
            "cronometro_inicio",
            "status",
            "concluida",
            "concluida_em",
            "atualizado_em",
        ]
    )
    return atividade


def parar_cronometro(atividade: AtividadeDiaria) -> AtividadeDiaria:
    if not atividade.cronometro_inicio:
        return atividade
    decorrido = max(
        0, int((timezone.now() - atividade.cronometro_inicio).total_seconds())
    )
    atividade.tempo_acumulado_segundos = (
        int(atividade.tempo_acumulado_segundos or 0) + decorrido
    )
    atividade.cronometro_inicio = None
    atividade.save(
        update_fields=["tempo_acumulado_segundos", "cronometro_inicio", "atualizado_em"]
    )
    return atividade


def alternar_cronometro(atividade: AtividadeDiaria, ator: Funcionario) -> AtividadeDiaria:
    if atividade.cronometro_inicio:
        return parar_cronometro(atividade)
    return iniciar_cronometro(atividade, ator)


def formatar_tempo(segundos: int) -> str:
    s = max(0, int(segundos or 0))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def resumo_visivel(
    ator: Funcionario,
    *,
    escopo: str = "minhas",
    responsavel_id: int | None = None,
    dia: date | None = None,
) -> dict:
    qs = queryset_visivel(ator, escopo=escopo, responsavel_id=responsavel_id)
    # Mesmo recorte da lista (senão o Total fica maior que os grupos do dia)
    if dia is not None:
        qs = qs.filter(Q(planejado_para=dia) | Q(data_vencimento=dia))
    agg = qs.aggregate(
        total=Count("id"),
        realizados=Count("id", filter=Q(status=StatusAtividade.REALIZADO)),
        executando=Count("id", filter=Q(status=StatusAtividade.EXECUTANDO)),
        urgentes=Count(
            "id",
            filter=Q(
                prioridade=PrioridadeAtividade.URGENTE,
            )
            & ~Q(status=StatusAtividade.REALIZADO),
        ),
    )
    total = agg["total"] or 0
    feitos = agg["realizados"] or 0
    return {
        "total": total,
        "realizados": feitos,
        "executando": agg["executando"] or 0,
        "urgentes": agg["urgentes"] or 0,
        "percentual": int(round((feitos / total) * 100)) if total else 0,
    }


def historico_planner(ator: Funcionario, *, dias: int = 7) -> list[dict]:
    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=dias - 1)
    qs = queryset_visivel(ator, escopo="minhas").filter(
        planejado_para__gte=inicio,
        planejado_para__lte=hoje,
    )
    rows = (
        qs.values("planejado_para")
        .annotate(
            total=Count("id"),
            concluidas=Count("id", filter=Q(status=StatusAtividade.REALIZADO)),
        )
        .order_by("-planejado_para")
    )
    return [
        {
            "data": row["planejado_para"],
            "total": row["total"],
            "concluidas": row["concluidas"],
            "percentual": (
                int(round((row["concluidas"] / row["total"]) * 100))
                if row["total"]
                else 0
            ),
        }
        for row in rows
        if row["planejado_para"]
    ]


def obter_ou_criar_dia(funcionario: Funcionario, dia: date | None = None) -> DiaPlanner:
    dia = dia or timezone.localdate()
    obj, _created = DiaPlanner.objects.get_or_create(
        funcionario=funcionario,
        data=dia,
    )
    chaves_padrao = {chave for chave, _ in HABITOS_PADRAO}
    existentes = set(obj.habitos.values_list("chave", flat=True))
    faltando = chaves_padrao - existentes
    if faltando:
        HabitoDia.objects.bulk_create(
            [HabitoDia(dia=obj, chave=chave) for chave in faltando]
        )
    # Remove hábitos antigos que saíram do padrão
    obsoletos = existentes - chaves_padrao
    if obsoletos:
        obj.habitos.filter(chave__in=obsoletos).delete()
    return obj


def definir_agua(dia_obj: DiaPlanner, copos: int) -> DiaPlanner:
    dia_obj.agua_copos = max(0, min(COPOS_AGUA_META, int(copos)))
    dia_obj.save(update_fields=["agua_copos", "atualizado_em"])
    return dia_obj


def alternar_habito(dia_obj: DiaPlanner, chave: str) -> HabitoDia:
    habito, _ = HabitoDia.objects.get_or_create(dia=dia_obj, chave=chave)
    habito.feito = not habito.feito
    habito.save(update_fields=["feito"])
    return habito


def adicionar_meta(dia_obj: DiaPlanner, texto: str) -> MetaFoco:
    ordem = dia_obj.metas.count()
    return MetaFoco.objects.create(dia=dia_obj, texto=texto.strip(), ordem=ordem)


def alternar_meta(meta: MetaFoco) -> MetaFoco:
    meta.concluida = not meta.concluida
    meta.save(update_fields=["concluida"])
    return meta


def matriz_eisenhower(itens) -> list[dict]:
    labels = {
        QuadranteEisenhower.FAZER: ("1. Fazer primeiro", "Urgente e importante"),
        QuadranteEisenhower.AGENDAR: ("2. Agendar", "Importante, não urgente"),
        QuadranteEisenhower.DELEGAR: ("3. Delegar", "Urgente, menos importante"),
        QuadranteEisenhower.ELIMINAR: ("4. Eliminar", "Nem urgente nem importante"),
    }
    buckets = {q: [] for q in QuadranteEisenhower.values}
    for item in itens:
        q = item.quadrante or QuadranteEisenhower.AGENDAR
        if q not in buckets:
            q = QuadranteEisenhower.AGENDAR
        buckets[q].append(item)
    return [
        {
            "chave": chave,
            "titulo": labels[chave][0],
            "subtitulo": labels[chave][1],
            "itens": buckets[chave][:6],
            "count": len(buckets[chave]),
        }
        for chave in (
            QuadranteEisenhower.FAZER,
            QuadranteEisenhower.AGENDAR,
            QuadranteEisenhower.DELEGAR,
            QuadranteEisenhower.ELIMINAR,
        )
    ]


def agenda_do_dia(itens) -> list[dict]:
    """Blocos com horário para a timeline 06–22."""
    blocos = []
    for item in itens:
        if item.hora_inicio:
            blocos.append(
                {
                    "titulo": item.titulo,
                    "inicio": item.hora_inicio,
                    "fim": item.hora_fim,
                    "status": item.status,
                    "pk": item.pk,
                }
            )
    blocos.sort(key=lambda b: b["inicio"])
    return blocos


def metricas_planner(funcionario: Funcionario, dia: date, itens) -> dict:
    lista = list(itens) if not isinstance(itens, list) else itens
    total = len(lista)
    feitos = sum(1 for i in lista if i.status == StatusAtividade.REALIZADO)
    em_andamento = sum(1 for i in lista if i.status == StatusAtividade.EXECUTANDO)
    pendentes = max(0, total - feitos - em_andamento)
    foco_seg = sum(i.tempo_atual_segundos() for i in lista)
    pct = int(round((feitos / total) * 100)) if total else 0
    # Focus score 0–10 a partir de conclusão + tempo
    score = 0.0
    if total:
        score += (feitos / total) * 7
    score += min(3.0, (foco_seg / 3600) * 0.75)
    return {
        "total": total,
        "feitos": feitos,
        "em_andamento": em_andamento,
        "pendentes": pendentes,
        "percentual": pct,
        "focus_score": round(min(10.0, score), 1),
        "focus_time": formatar_tempo(foco_seg),
        "focus_segundos": foco_seg,
        "pct_feitos": pct,
        "pct_andamento": int(round((em_andamento / total) * 100)) if total else 0,
        "pct_pendentes": int(round((pendentes / total) * 100)) if total else 0,
    }


def semana_habitos(funcionario: Funcionario, dia: date) -> dict:
    """Grade M–D da semana contendo o dia."""
    inicio = dia - timedelta(days=dia.weekday())  # segunda
    dias = [inicio + timedelta(days=i) for i in range(7)]
    registros = {
        (h.dia.data, h.chave): h.feito
        for h in HabitoDia.objects.filter(
            dia__funcionario=funcionario,
            dia__data__in=dias,
        ).select_related("dia")
    }
    cols = []
    for d in dias:
        cols.append(
            {
                "data": d,
                "label": d.strftime("%a")[:1].upper(),
                "eh_hoje": d == dia,
            }
        )
    linhas = []
    for chave, nome in HABITOS_PADRAO:
        linhas.append(
            {
                "chave": chave,
                "nome": nome,
                "dias": [
                    {"data": d, "feito": bool(registros.get((d, chave)))} for d in dias
                ],
            }
        )
    return {"cols": cols, "linhas": linhas}


def resumo_agua_habitos_semana(funcionario: Funcionario, dia: date | None = None) -> dict:
    """Água de hoje + contagem dos hábitos na semana (para a dashboard)."""
    dia = dia or timezone.localdate()
    inicio = dia - timedelta(days=dia.weekday())
    dias = [inicio + timedelta(days=i) for i in range(7)]
    dias_planner = {
        row.data: row
        for row in DiaPlanner.objects.filter(funcionario=funcionario, data__in=dias)
    }
    hoje_obj = dias_planner.get(dia)
    agua_hoje = int(hoje_obj.agua_copos) if hoje_obj else 0
    agua_semana_copos = sum(int(d.agua_copos or 0) for d in dias_planner.values())
    meta_copos = COPOS_AGUA_META
    meta_ml = meta_copos * ML_POR_COPO
    agua_hoje_ml = agua_hoje * ML_POR_COPO
    agua_semana_ml = agua_semana_copos * ML_POR_COPO
    dias_com_agua = sum(1 for d in dias_planner.values() if (d.agua_copos or 0) > 0)
    pct_agua = int(round((agua_hoje / meta_copos) * 100)) if meta_copos else 0

    registros = {
        (h.dia.data, h.chave): h.feito
        for h in HabitoDia.objects.filter(
            dia__funcionario=funcionario,
            dia__data__in=dias,
        ).select_related("dia")
    }
    total_possivel = len(HABITOS_PADRAO) * 7
    feitos_semana = 0
    habitos = []
    for chave, nome in HABITOS_PADRAO:
        dias_feito = []
        feitos = 0
        for d in dias:
            ok = bool(registros.get((d, chave)))
            if ok:
                feitos += 1
            dias_feito.append(
                {
                    "data": d,
                    "label": d.strftime("%a")[:1].upper(),
                    "feito": ok,
                    "eh_hoje": d == dia,
                }
            )
        feitos_semana += feitos
        habitos.append(
            {
                "chave": chave,
                "nome": nome,
                "feitos": feitos,
                "meta": 7,
                "pct": int(round((feitos / 7) * 100)) if feitos else 0,
                "dias": dias_feito,
            }
        )

    feitos_hoje = sum(1 for chave, _ in HABITOS_PADRAO if registros.get((dia, chave)))
    total_hoje = len(HABITOS_PADRAO)
    pct_habitos = (
        int(round((feitos_semana / total_possivel) * 100)) if total_possivel else 0
    )

    return {
        "agua_hoje_copos": agua_hoje,
        "agua_meta_copos": meta_copos,
        "agua_hoje_ml": agua_hoje_ml,
        "agua_meta_ml": meta_ml,
        "agua_pct": min(100, pct_agua),
        "agua_copos_ui": agua_copos_ui(agua_hoje),
        "agua_semana_copos": agua_semana_copos,
        "agua_semana_ml": agua_semana_ml,
        "agua_dias_com_registro": dias_com_agua,
        "habitos": habitos,
        "habitos_feitos_semana": feitos_semana,
        "habitos_meta_semana": total_possivel,
        "habitos_pct_semana": pct_habitos,
        "habitos_feitos_hoje": feitos_hoje,
        "habitos_meta_hoje": total_hoje,
        "inicio_semana": inicio,
        "fim_semana": dias[-1],
    }


def agua_copos_ui(copos: int) -> list[dict]:
    atual = max(0, min(COPOS_AGUA_META, int(copos or 0)))
    return [
        {
            "n": i,
            "cheio": i <= atual,
            "ml": ML_POR_COPO,
            # Clique no último cheio remove 1; senão define até este copo
            "definir": (atual - 1) if i == atual and atual > 0 else i,
        }
        for i in range(1, COPOS_AGUA_META + 1)
    ]


def agenda_por_hora(itens, inicio: int = 6, fim: int = 22) -> list[dict]:
    from collections import defaultdict

    buckets: dict[int, list] = defaultdict(list)
    for item in itens:
        if not item.hora_inicio:
            continue
        h = item.hora_inicio.hour
        if inicio <= h <= fim:
            buckets[h].append(
                {
                    "titulo": item.titulo,
                    "inicio": item.hora_inicio,
                    "fim": item.hora_fim,
                    "pk": item.pk,
                }
            )
    return [
        {
            "hora": f"{h:02d}:00",
            "blocos": buckets.get(h, []),
        }
        for h in range(inicio, fim + 1)
    ]


def horas_timeline(inicio: int = 6, fim: int = 22) -> list[str]:
    return [f"{h:02d}:00" for h in range(inicio, fim + 1)]
