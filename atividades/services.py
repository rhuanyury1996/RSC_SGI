from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, QuerySet, When
from django.utils import timezone

from funcionarios.models import Funcionario

from .models import (
    COPOS_AGUA_META,
    HABITOS_PADRAO,
    ML_POR_COPO,
    STATUS_ORDEM,
    AtividadeDiaria,
    DiaPlanner,
    EventoAtividade,
    HabitoDia,
    MetaFoco,
    PrioridadeAtividade,
    QuadranteEisenhower,
    SessaoTempoAtividade,
    StatusAtividade,
    TipoEventoAtividade,
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


def q_aparece_no_dia(dia: date, hoje: date | None = None) -> Q:
    """Tarefas do dia, mais as atrasadas em aberto quando o dia é hoje."""
    hoje = hoje or timezone.localdate()
    q = Q(planejado_para=dia) | Q(data_vencimento=dia)
    if dia == hoje:
        q = q | (
            ~Q(status=StatusAtividade.REALIZADO)
            & (Q(planejado_para__lt=hoje) | Q(data_vencimento__lt=hoje))
        )
    return q


def queryset_visivel(
    ator: Funcionario,
    *,
    escopo: str = "equipe",
    responsavel_id: int | None = None,
    pessoas_ids: list[int] | None = None,
) -> QuerySet[AtividadeDiaria]:
    """Leitura do time inteiro. 'minhas' e pessoas são filtros, não permissão."""
    subtarefas = AtividadeDiaria.objects.filter(deletado_em__isnull=True).select_related(
        "responsavel"
    ).prefetch_related("participantes")
    qs = (
        AtividadeDiaria.objects.ativas()
        .select_related("responsavel", "criado_por", "cliente_rsc", "atividade_pai")
        .prefetch_related(
            "participantes",
            Prefetch("subtarefas", queryset=subtarefas),
        )
    )
    if escopo == "minhas":
        qs = qs.filter(_q_membro(ator.pk))
    elif responsavel_id:
        qs = qs.filter(_q_membro(responsavel_id))
    if pessoas_ids:
        q_pessoas = Q()
        for pid in pessoas_ids:
            q_pessoas |= _q_membro(pid)
        qs = qs.filter(q_pessoas)
    return qs.distinct()


def atividades_filtradas(
    ator: Funcionario,
    *,
    escopo: str = "equipe",
    responsavel_id: int | None = None,
    dia: date | None = None,
    organizacao: str = "status",
    pessoas_ids: list[int] | None = None,
    texto: str = "",
    empresa_id: int | None = None,
    periodo: str | None = None,
) -> QuerySet[AtividadeDiaria]:
    qs = queryset_visivel(
        ator,
        escopo=escopo,
        responsavel_id=responsavel_id,
        pessoas_ids=pessoas_ids,
    )
    hoje = timezone.localdate()
    if periodo == "abertas":
        qs = qs.filter(
            ~Q(status=StatusAtividade.REALIZADO)
            | Q(planejado_para=hoje)
            | Q(data_vencimento=hoje)
            | Q(concluida_em__date=hoje)
        )
    elif periodo == "semana":
        inicio = hoje - timedelta(days=hoje.weekday())
        fim = inicio + timedelta(days=6)
        qs = qs.filter(
            Q(planejado_para__range=(inicio, fim))
            | Q(data_vencimento__range=(inicio, fim))
            | (
                ~Q(status=StatusAtividade.REALIZADO)
                & (Q(planejado_para__lt=hoje) | Q(data_vencimento__lt=hoje))
            )
        )
    elif dia is not None:
        qs = qs.filter(q_aparece_no_dia(dia, hoje))
    if texto:
        qs = qs.filter(Q(titulo__icontains=texto) | Q(descricao__icontains=texto))
    if empresa_id:
        qs = qs.filter(cliente_rsc_id=empresa_id)
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


def montar_quadro(itens, agrupamento: str, membros: list[Funcionario]) -> list[dict]:
    """Colunas de status, com faixas opcionais por pessoa ou prioridade."""
    lista = list(itens)

    def _faixa(ident, label, blocos, pessoa=None):
        colunas = agrupar_por_status(blocos)
        return {
            "id": ident,
            "label": label,
            "pessoa": pessoa,
            "count": len(list(blocos) if not isinstance(blocos, list) else blocos),
            "colunas": colunas,
        }

    if agrupamento == "pessoa":
        faixas = []
        for grupo in agrupar_por_pessoa(lista, membros):
            faixas.append(
                _faixa(
                    grupo["status"],
                    grupo["label"],
                    grupo["itens"],
                    pessoa=grupo.get("pessoa"),
                )
            )
        return faixas
    if agrupamento == "prioridade":
        return [
            _faixa(grupo["status"], grupo["label"], grupo["itens"])
            for grupo in agrupar_por_prioridade(lista)
        ]
    return [_faixa("status", "", lista)]


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


def registrar_evento(
    atividade: AtividadeDiaria,
    autor: Funcionario | None,
    tipo: str,
    *,
    texto: str = "",
    de_status: str = "",
    para_status: str = "",
) -> EventoAtividade:
    return EventoAtividade.objects.create(
        atividade=atividade,
        autor=autor,
        tipo=tipo,
        texto=(texto or "").strip(),
        de_status=de_status or "",
        para_status=para_status or "",
    )


def aviso_sobreposicao(
    responsavel: Funcionario | None,
    dia: date | None,
    inicio,
    fim,
    *,
    ignorar_pk: int | None = None,
) -> str:
    """Aviso, sem bloquear, quando a mesma pessoa tem horários sobrepostos."""
    if not responsavel or not dia or not inicio or not fim:
        return ""
    qs = AtividadeDiaria.objects.ativas().filter(
        responsavel=responsavel,
        planejado_para=dia,
        hora_inicio__isnull=False,
        hora_fim__isnull=False,
    )
    if ignorar_pk:
        qs = qs.exclude(pk=ignorar_pk)
    for outra in qs:
        if inicio < outra.hora_fim and fim > outra.hora_inicio:
            return (
                f"{responsavel.nome_completo} já tem “{outra.titulo}” "
                f"entre {outra.hora_inicio.strftime('%H:%M')} e {outra.hora_fim.strftime('%H:%M')}."
            )
    return ""


def criar_atividade(
    ator: Funcionario,
    *,
    titulo: str,
    responsavel: Funcionario | None = None,
    participantes=None,
    atividade_pai: AtividadeDiaria | None = None,
    status: str = StatusAtividade.NAO_INICIADO,
    prioridade: str = PrioridadeAtividade.MEDIA,
    quadrante: str | None = None,
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
    quad = quadrante if quadrante in QuadranteEisenhower.values else QuadranteEisenhower.AGENDAR
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
        quadrante=quad,
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
    registrar_evento(
        item,
        ator,
        TipoEventoAtividade.CRIACAO,
        texto="Criou a tarefa.",
        para_status=item.status,
    )
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


def alterar_status(
    atividade: AtividadeDiaria,
    status: str,
    *,
    autor: Funcionario | None = None,
) -> AtividadeDiaria:
    if status not in StatusAtividade.values:
        return atividade
    anterior = atividade.status
    if (
        status in (StatusAtividade.REALIZADO, StatusAtividade.EM_REVISAO)
        and atividade.cronometro_inicio
    ):
        parar_cronometro(atividade, ator=autor)
        atividade.refresh_from_db()
    if anterior == status:
        return atividade
    atividade.status = status
    atividade.sincronizar_conclusao()
    atividade.save(
        update_fields=["status", "concluida", "concluida_em", "atualizado_em"]
    )
    registrar_evento(
        atividade,
        autor,
        TipoEventoAtividade.STATUS,
        texto=f"{StatusAtividade(anterior).label} → {StatusAtividade(status).label}",
        de_status=anterior,
        para_status=status,
    )
    return atividade


def excluir_atividade(
    atividade: AtividadeDiaria,
    autor: Funcionario | None = None,
) -> None:
    if atividade.cronometro_inicio:
        parar_cronometro(atividade, ator=autor)
        atividade.refresh_from_db()
    agora = timezone.now()
    filhos = list(atividade.subtarefas.filter(deletado_em__isnull=True))
    atividade.deletado_em = agora
    atividade.deletado_por = autor
    atividade.save(update_fields=["deletado_em", "deletado_por", "atualizado_em"])
    for filho in filhos:
        filho.deletado_em = agora
        filho.deletado_por = autor
        filho.save(update_fields=["deletado_em", "deletado_por", "atualizado_em"])
    registrar_evento(
        atividade,
        autor,
        TipoEventoAtividade.EXCLUSAO,
        texto="Excluiu a tarefa.",
    )


def restaurar_atividade(
    atividade: AtividadeDiaria,
    autor: Funcionario | None = None,
) -> AtividadeDiaria:
    marco = atividade.deletado_em
    atividade.deletado_em = None
    atividade.deletado_por = None
    atividade.save(update_fields=["deletado_em", "deletado_por", "atualizado_em"])
    if marco is not None:
        atividade.subtarefas.filter(deletado_em=marco).update(
            deletado_em=None,
            deletado_por=None,
        )
    registrar_evento(
        atividade,
        autor,
        TipoEventoAtividade.RESTAURACAO,
        texto="Desfez a exclusão.",
    )
    return atividade


def _fechar_sessoes_abertas(
    atividade: AtividadeDiaria,
    *,
    ator: Funcionario | None = None,
    fim=None,
) -> int:
    """Fecha sessões abertas e devolve segundos creditados nesta parada."""
    agora = fim or timezone.now()
    qs = SessaoTempoAtividade.objects.filter(atividade=atividade, fim__isnull=True)
    if ator is not None:
        preferida = qs.filter(funcionario=ator).order_by("-inicio").first()
        abertas = [preferida] if preferida else list(qs.order_by("-inicio")[:1])
    else:
        abertas = list(qs.order_by("inicio"))
    total = 0
    for sessao in abertas:
        if sessao is None:
            continue
        decorrido = max(0, int((agora - sessao.inicio).total_seconds()))
        sessao.fim = agora
        sessao.segundos = decorrido
        sessao.save(update_fields=["fim", "segundos"])
        total += decorrido
    return total


def iniciar_cronometro(atividade: AtividadeDiaria, ator: Funcionario) -> AtividadeDiaria:
    if atividade.status == StatusAtividade.REALIZADO:
        return atividade
    # Um cronômetro por usuário: pausa só as sessões que esta pessoa abriu.
    abertas = list(
        SessaoTempoAtividade.objects.filter(funcionario=ator, fim__isnull=True)
        .exclude(atividade_id=atividade.pk)
        .select_related("atividade")
    )
    for sessao in abertas:
        parar_cronometro(sessao.atividade, ator=ator)

    if atividade.cronometro_inicio:
        return atividade

    if atividade.status == StatusAtividade.NAO_INICIADO:
        atividade.status = StatusAtividade.EXECUTANDO
        atividade.sincronizar_conclusao()

    agora = timezone.now()
    atividade.cronometro_inicio = agora
    atividade.save(
        update_fields=[
            "cronometro_inicio",
            "status",
            "concluida",
            "concluida_em",
            "atualizado_em",
        ]
    )
    SessaoTempoAtividade.objects.create(
        atividade=atividade,
        funcionario=ator,
        inicio=agora,
    )
    return atividade


def parar_cronometro(
    atividade: AtividadeDiaria,
    ator: Funcionario | None = None,
) -> AtividadeDiaria:
    if not atividade.cronometro_inicio:
        _fechar_sessoes_abertas(atividade, ator=ator)
        return atividade
    agora = timezone.now()
    decorrido_sessao = _fechar_sessoes_abertas(atividade, ator=ator, fim=agora)
    decorrido = decorrido_sessao or max(
        0, int((agora - atividade.cronometro_inicio).total_seconds())
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
        return parar_cronometro(atividade, ator=ator)
    return iniciar_cronometro(atividade, ator)


def tempo_por_funcionario_periodo(
    funcionario: Funcionario,
    inicio,
    fim,
) -> list[dict]:
    """Tempo em atividades no período (sessões + cronômetro aberto)."""
    from datetime import datetime, time as time_cls

    tz = timezone.get_current_timezone()
    ini_dt = timezone.make_aware(datetime.combine(inicio, time_cls.min), tz)
    fim_dt = timezone.make_aware(datetime.combine(fim, time_cls.max), tz)

    sessoes = (
        SessaoTempoAtividade.objects.filter(funcionario=funcionario)
        .filter(inicio__lte=fim_dt)
        .filter(Q(fim__gte=ini_dt) | Q(fim__isnull=True))
        .select_related("atividade", "atividade__cliente_rsc", "atividade__responsavel")
        .order_by("atividade_id", "inicio")
    )
    por_atividade: dict[int, dict] = {}
    for sessao in sessoes:
        # Recorta a sessão ao período
        s_ini = max(sessao.inicio, ini_dt)
        s_fim = sessao.fim or timezone.now()
        s_fim = min(s_fim, fim_dt)
        segs = max(0, int((s_fim - s_ini).total_seconds()))
        if segs <= 0:
            continue
        aid = sessao.atividade_id
        row = por_atividade.get(aid)
        if row is None:
            at = sessao.atividade
            row = {
                "atividade": at,
                "titulo": at.titulo,
                "empresa": at.empresa_label,
                "status": at.status,
                "status_label": at.get_status_display(),
                "segundos": 0,
            }
            por_atividade[aid] = row
        row["segundos"] += segs

    itens = sorted(
        por_atividade.values(),
        key=lambda r: (-r["segundos"], r["titulo"].lower()),
    )
    for row in itens:
        row["tempo_fmt"] = formatar_tempo(row["segundos"])
    return itens


def formatar_tempo(segundos: int) -> str:
    s = max(0, int(segundos or 0))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}"


def resumo_visivel(
    ator: Funcionario,
    *,
    escopo: str = "equipe",
    responsavel_id: int | None = None,
    dia: date | None = None,
    pessoas_ids: list[int] | None = None,
    texto: str = "",
    empresa_id: int | None = None,
    periodo: str | None = None,
) -> dict:
    hoje = timezone.localdate()
    qs = atividades_filtradas(
        ator,
        escopo=escopo,
        responsavel_id=responsavel_id,
        dia=dia,
        pessoas_ids=pessoas_ids,
        texto=texto,
        empresa_id=empresa_id,
        periodo=periodo,
    )
    agg = qs.aggregate(
        total=Count("id", distinct=True),
        realizados=Count(
            "id",
            filter=Q(status=StatusAtividade.REALIZADO),
            distinct=True,
        ),
        executando=Count(
            "id",
            filter=Q(status=StatusAtividade.EXECUTANDO),
            distinct=True,
        ),
        urgentes=Count(
            "id",
            filter=Q(prioridade=PrioridadeAtividade.URGENTE)
            & ~Q(status=StatusAtividade.REALIZADO),
            distinct=True,
        ),
        atrasadas=Count(
            "id",
            filter=~Q(status=StatusAtividade.REALIZADO)
            & (Q(planejado_para__lt=hoje) | Q(data_vencimento__lt=hoje)),
            distinct=True,
        ),
    )
    total = agg["total"] or 0
    feitos = agg["realizados"] or 0
    return {
        "total": total,
        "realizados": feitos,
        "executando": agg["executando"] or 0,
        "urgentes": agg["urgentes"] or 0,
        "atrasadas": agg["atrasadas"] or 0,
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
        letras = "STQQSSD"
        cols.append(
            {
                "data": d,
                "label": letras[d.weekday()],
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
                    "label": "STQQSSD"[d.weekday()],
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


def eventos_calendario_do_dia(funcionario: Funcionario, dia: date) -> list:
    """Eventos do calendário (reuniões etc.) no dia, para a agenda do planner."""
    from calendario.models import EventoCalendario

    return list(
        EventoCalendario.objects.filter(
            funcionario=funcionario,
            inicio__date__lte=dia,
            fim__date__gte=dia,
        )
        .exclude(status="cancelado")
        .order_by("inicio")
    )


def agenda_por_hora(
    itens,
    inicio: int = 6,
    fim: int = 22,
    *,
    eventos=None,
) -> list[dict]:
    from collections import defaultdict
    from datetime import time as time_cls

    buckets: dict[int, list] = defaultdict(list)
    for item in itens:
        if not item.hora_inicio:
            continue
        h = item.hora_inicio.hour
        if inicio <= h <= fim:
            minutos = 60
            if item.hora_fim:
                minutos = (
                    item.hora_fim.hour * 60
                    + item.hora_fim.minute
                    - (item.hora_inicio.hour * 60 + item.hora_inicio.minute)
                )
                minutos = max(30, minutos)
            buckets[h].append(
                {
                    "titulo": item.titulo,
                    "inicio": item.hora_inicio,
                    "fim": item.hora_fim,
                    "pk": item.pk,
                    "tipo": "atividade",
                    "tipo_label": "Tarefa",
                    "cor": "",
                    "altura": max(32, int(minutos / 60 * 36)),
                    "faixa": (
                        f"{item.hora_inicio.strftime('%H:%M')}–{item.hora_fim.strftime('%H:%M')}"
                        if item.hora_fim
                        else item.hora_inicio.strftime("%H:%M")
                    ),
                }
            )

    for ev in eventos or []:
        ini_local = timezone.localtime(ev.inicio)
        fim_local = timezone.localtime(ev.fim)
        if getattr(ev, "dia_inteiro", False):
            h = inicio
            hora_ini = time_cls(inicio, 0)
            hora_fim = None
        else:
            h = ini_local.hour
            if h < inicio or h > fim:
                continue
            hora_ini = ini_local.time()
            hora_fim = fim_local.time() if fim_local.date() == ini_local.date() else None
        tipo = getattr(ev, "tipo", "") or "evento"
        minutos = 60
        if hora_fim and hora_ini:
            minutos = max(
                30,
                (hora_fim.hour * 60 + hora_fim.minute)
                - (hora_ini.hour * 60 + hora_ini.minute),
            )
        buckets[h].append(
            {
                "titulo": ev.titulo,
                "inicio": hora_ini,
                "fim": hora_fim,
                "pk": ev.pk,
                "tipo": tipo,
                "tipo_label": (
                    ev.get_tipo_display() if hasattr(ev, "get_tipo_display") else tipo
                ),
                "cor": getattr(ev, "cor", "") or "",
                "altura": max(32, int(minutos / 60 * 36)),
                "faixa": (
                    f"{hora_ini.strftime('%H:%M')}–{hora_fim.strftime('%H:%M')}"
                    if hora_fim
                    else hora_ini.strftime("%H:%M")
                ),
            }
        )

    for h, lista in buckets.items():
        lista.sort(key=lambda b: (b["inicio"] is None, b["inicio"] or time_cls.min))

    return [
        {
            "hora": f"{h:02d}:00",
            "blocos": buckets.get(h, []),
        }
        for h in range(inicio, fim + 1)
    ]


def horas_timeline(inicio: int = 6, fim: int = 22) -> list[str]:
    return [f"{h:02d}:00" for h in range(inicio, fim + 1)]
