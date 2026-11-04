from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Case, F, IntegerField, Prefetch, Q, QuerySet, When
from django.utils import timezone

from funcionarios.models import Funcionario

from .models import (
    COPOS_AGUA_META,
    HABITOS_PADRAO,
    ML_POR_COPO,
    STATUS_CONCLUIDOS,
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
        When(prioridade=PrioridadeAtividade.BAIXA, then=3),
        default=4,
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
            ~Q(status__in=STATUS_CONCLUIDOS)
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
    sessoes = Prefetch(
        "sessoes_tempo",
        queryset=SessaoTempoAtividade.objects.order_by("inicio"),
        to_attr="sessoes_pref",
    )
    subtarefas = AtividadeDiaria.objects.filter(deletado_em__isnull=True).select_related(
        "responsavel"
    ).prefetch_related("participantes", sessoes).order_by("criado_em", "id")
    qs = (
        AtividadeDiaria.objects.ativas()
        .select_related("responsavel", "criado_por", "cliente_rsc", "atividade_pai")
        .prefetch_related(
            "participantes",
            sessoes,
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
        status
        in (
            StatusAtividade.REALIZADO,
            StatusAtividade.COMPLETE,
            StatusAtividade.EM_REVISAO,
            StatusAtividade.LIBERADO,
        )
        and atividade.cronometro_inicio
    ):
        parar_cronometro(atividade, ator=None)
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
        parar_cronometro(atividade, ator=None)
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


def _sincronizar_inicio(atividade: AtividadeDiaria) -> None:
    """cronometro_inicio = início da sessão aberta mais antiga (ou None)."""
    abertas = SessaoTempoAtividade.objects.filter(
        atividade=atividade, fim__isnull=True
    ).order_by("inicio")
    primeira = abertas.first()
    atividade.cronometro_inicio = primeira.inicio if primeira else None


def _fechar_sessoes_abertas(
    atividade: AtividadeDiaria,
    *,
    ator: Funcionario | None = None,
    fim=None,
) -> int:
    """Fecha as sessões abertas de `ator` (ou de todos, se None) nesta tarefa.

    Devolve os segundos creditados. Nunca fecha a sessão de outra pessoa
    quando `ator` é informado.
    """
    agora = fim or timezone.now()
    qs = SessaoTempoAtividade.objects.filter(atividade=atividade, fim__isnull=True)
    if ator is not None:
        qs = qs.filter(funcionario=ator)
    total = 0
    for sessao in qs:
        decorrido = max(0, int((agora - sessao.inicio).total_seconds()))
        sessao.fim = agora
        sessao.segundos = decorrido
        sessao.save(update_fields=["fim", "segundos"])
        total += decorrido
    return total


def _tem_sessao_aberta(atividade: AtividadeDiaria, ator: Funcionario | None = None) -> bool:
    qs = SessaoTempoAtividade.objects.filter(atividade=atividade, fim__isnull=True)
    if ator is not None:
        qs = qs.filter(funcionario=ator)
    return qs.exists()


def iniciar_cronometro(atividade: AtividadeDiaria, ator: Funcionario) -> AtividadeDiaria:
    """Inicia o cronômetro da pessoa nesta tarefa (outras pessoas seguem o delas)."""
    if atividade.status in STATUS_CONCLUIDOS:
        return atividade
    # Uma pessoa cronometra uma tarefa por vez: pausa as dela nas outras tarefas.
    outras = list(
        SessaoTempoAtividade.objects.filter(funcionario=ator, fim__isnull=True)
        .exclude(atividade_id=atividade.pk)
        .select_related("atividade")
    )
    for sessao in outras:
        parar_cronometro(sessao.atividade, ator=ator)

    if _tem_sessao_aberta(atividade, ator):
        return atividade
    # Cronômetro antigo (sem sessão): encerra antes de abrir o por pessoa.
    if atividade.cronometro_inicio and not _tem_sessao_aberta(atividade):
        parar_cronometro(atividade, ator=None)
        atividade.refresh_from_db()

    if atividade.status in (StatusAtividade.NAO_INICIADO, StatusAtividade.ORGANIZANDO):
        atividade.status = StatusAtividade.EXECUTANDO
        atividade.sincronizar_conclusao()

    SessaoTempoAtividade.objects.create(
        atividade=atividade,
        funcionario=ator,
        inicio=timezone.now(),
    )
    _sincronizar_inicio(atividade)
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


def parar_cronometro(
    atividade: AtividadeDiaria,
    ator: Funcionario | None = None,
) -> AtividadeDiaria:
    """Para o cronômetro de `ator` nesta tarefa; com ator=None, para o de todos."""
    agora = timezone.now()
    legado = atividade.cronometro_inicio is not None and not _tem_sessao_aberta(atividade)
    decorrido = _fechar_sessoes_abertas(atividade, ator=ator, fim=agora)
    if legado:
        decorrido += max(0, int((agora - atividade.cronometro_inicio).total_seconds()))
    atividade.tempo_acumulado_segundos = (
        int(atividade.tempo_acumulado_segundos or 0) + decorrido
    )
    _sincronizar_inicio(atividade)
    atividade.save(
        update_fields=["tempo_acumulado_segundos", "cronometro_inicio", "atualizado_em"]
    )
    return atividade


def alternar_cronometro(atividade: AtividadeDiaria, ator: Funcionario) -> AtividadeDiaria:
    """Liga/desliga só o cronômetro de quem clicou."""
    if _tem_sessao_aberta(atividade, ator):
        return parar_cronometro(atividade, ator=ator)
    if atividade.cronometro_inicio and not _tem_sessao_aberta(atividade):
        return parar_cronometro(atividade, ator=None)
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


# ---------------------------------------------------------------------------
# Visualizações (Lista, Quadro, Gantt, Mind Map): mesmos dados em JSON
# ---------------------------------------------------------------------------


def _iso(valor) -> str:
    return valor.isoformat() if valor else ""


def serializar_pessoa(f: Funcionario) -> dict:
    return {
        "id": f.pk,
        "nome": f.nome_completo,
        "iniciais": f"{(f.nome or '')[:1]}{(f.sobrenome or '')[:1]}".upper() or "?",
        "ativo": bool(getattr(f, "ativo", True)),
    }


def serializar_atividade(
    item: AtividadeDiaria,
    ator: Funcionario,
    *,
    hoje: date | None = None,
    com_subtarefas: bool = True,
) -> dict:
    hoje = hoje or timezone.localdate()
    participantes = [
        p.pk for p in item.participantes.all() if p.pk != item.responsavel_id
    ]
    # Mesmas regras de permissions.py, sem consulta extra por tarefa.
    na_equipe = item.responsavel_id == ator.pk or ator.pk in participantes
    pode_editar = na_equipe or pode_dirigir_atividades(ator)
    pode_status = pode_editar or (bool(item.atividade_pai_id) and na_equipe)
    dado = {
        "id": item.pk,
        "titulo": item.titulo,
        "descricao": item.descricao or "",
        "status": item.status,
        "prioridade": item.prioridade,
        "responsavel": item.responsavel_id,
        "participantes": participantes,
        "empresa": item.cliente_rsc_id,
        "pai": item.atividade_pai_id,
        "planejado": _iso(item.planejado_para),
        "vencimento": _iso(item.data_vencimento),
        "entrega": _iso(item.data_entrega),
        "hora_inicio": item.hora_inicio.strftime("%H:%M") if item.hora_inicio else "",
        "hora_fim": item.hora_fim.strftime("%H:%M") if item.hora_fim else "",
        "quadrante": item.quadrante,
        "ordem": item.ordem,
        "atraso": _iso(item.data_atraso(hoje)),
        "segundos": item.tempo_atual_segundos(),
        # Base para o relógio ao vivo: total sem as sessões em andamento.
        "acumulado": item.tempo_atual_segundos() - item.segundos_em_andamento(),
        "rodando": [
            {"id": sessao.funcionario_id, "inicio": sessao.inicio.isoformat()}
            for sessao in item.sessoes_abertas()
        ],
        "timer_inicio": (
            minha.inicio.isoformat()
            if (minha := item.sessao_aberta_de(ator))
            else ""
        ),
        "por_pessoa": {str(k): v for k, v in item.tempo_por_pessoa().items()},
        "pode_editar": pode_editar,
        "pode_status": pode_status,
        "criado_em": item.criado_em.isoformat() if item.criado_em else "",
    }
    if com_subtarefas and not item.atividade_pai_id:
        dado["subtarefas"] = [
            serializar_atividade(sub, ator, hoje=hoje, com_subtarefas=False)
            for sub in item.subtarefas.all()
            if sub.deletado_em is None
        ]
    return dado


def tarefas_para_visualizacoes(ator: Funcionario) -> list[dict]:
    """Todas as tarefas raiz do time (subtarefas aninhadas), em ordem manual."""
    hoje = timezone.localdate()
    qs = (
        queryset_visivel(ator, escopo="equipe")
        .filter(atividade_pai__isnull=True)
        .annotate(prio_rank=_prio_rank())
        .order_by("ordem", "-criado_em", "-id")
    )
    return [serializar_atividade(item, ator, hoje=hoje) for item in qs]


def reordenar_atividades(ids: list[int]) -> None:
    """Grava a ordem manual (arrastar) de um grupo/coluna."""
    for posicao, pk in enumerate(ids):
        AtividadeDiaria.objects.filter(pk=pk).update(ordem=posicao)


def relogio_para(item: AtividadeDiaria, funcionario: Funcionario | None) -> dict:
    """Cronômetro da tarefa do ponto de vista de uma pessoa.

    `ativo` diz se o cronômetro DESTA pessoa está rodando. `segundos` é o total
    da tarefa (todos). `acumulado` + (agora - `inicio`) reproduz o total ao vivo
    no navegador, avançando no ritmo da sessão desta pessoa.
    """
    minha = item.sessao_aberta_de(funcionario)
    total = item.tempo_atual_segundos()
    ativo = minha is not None or (
        item._cronometro_legado() and item.faz_parte_da_equipe(funcionario)
    )
    if minha is not None:
        inicio = minha.inicio
    elif ativo:
        inicio = item.cronometro_inicio
    else:
        inicio = None
    decorrido = (
        max(0, int((timezone.now() - inicio).total_seconds())) if inicio else 0
    )
    return {
        "ativo": ativo,
        "segundos": total,
        "acumulado": max(0, total - decorrido),
        "inicio": inicio.isoformat() if inicio else "",
        "texto": formatar_tempo(total),
    }


# ---------------------------------------------------------------------------
# Tempo lançado à mão (esqueceu o cronômetro) e correção de registros
# ---------------------------------------------------------------------------

_DURACAO_RE = None


def interpretar_duracao(texto: str) -> int | None:
    """Aceita "1h30", "1h", "45min", "45m", "1:30", "90" (minutos). Devolve segundos."""
    import re

    global _DURACAO_RE
    if _DURACAO_RE is None:
        _DURACAO_RE = re.compile(
            r"^\s*(?:(?P<h>\d{1,3})\s*h(?:oras?)?)?\s*(?:(?P<m>\d{1,4})\s*(?:m|min|minutos?)?)?\s*$",
            re.IGNORECASE,
        )
    texto = (texto or "").strip().lower().replace(",", ".")
    if not texto:
        return None
    if ":" in texto:
        partes = texto.split(":")
        if len(partes) != 2 or not all(p.strip().isdigit() for p in partes):
            return None
        horas, minutos = int(partes[0]), int(partes[1])
        if minutos >= 60:
            return None
        total = horas * 3600 + minutos * 60
    else:
        try:
            # "1.5h" ou "1.5" horas
            if texto.endswith("h") and texto[:-1].replace(".", "", 1).isdigit():
                total = int(round(float(texto[:-1]) * 3600))
                return total if 0 < total <= 24 * 3600 else None
        except ValueError:
            return None
        m = _DURACAO_RE.match(texto)
        if not m or not (m.group("h") or m.group("m")):
            return None
        total = int(m.group("h") or 0) * 3600 + int(m.group("m") or 0) * 60
    return total if 0 < total <= 24 * 3600 else None


def _inicio_lancamento(dia: date, segundos: int):
    """Hoje: termina agora. Outro dia: começa às 09:00 daquele dia."""
    from datetime import datetime, time as time_cls

    tz = timezone.get_current_timezone()
    if dia == timezone.localdate():
        return timezone.now() - timedelta(seconds=segundos)
    return timezone.make_aware(datetime.combine(dia, time_cls(9, 0)), tz)


def _ajustar_acumulado(atividade: AtividadeDiaria, delta: int) -> None:
    atividade.tempo_acumulado_segundos = max(
        0, int(atividade.tempo_acumulado_segundos or 0) + int(delta)
    )
    atividade.save(update_fields=["tempo_acumulado_segundos", "atualizado_em"])


def lancar_tempo(
    atividade: AtividadeDiaria,
    funcionario: Funcionario,
    dia: date,
    segundos: int,
    autor: Funcionario,
) -> SessaoTempoAtividade:
    inicio = _inicio_lancamento(dia, segundos)
    sessao = SessaoTempoAtividade.objects.create(
        atividade=atividade,
        funcionario=funcionario,
        inicio=inicio,
        fim=inicio + timedelta(seconds=segundos),
        segundos=segundos,
        manual=True,
    )
    _ajustar_acumulado(atividade, segundos)
    quem = "" if funcionario.pk == autor.pk else f" para {funcionario.nome_completo}"
    registrar_evento(
        atividade,
        autor,
        TipoEventoAtividade.EDICAO,
        texto=f"Lançou {formatar_duracao(segundos)} de tempo{quem} em {dia.strftime('%d/%m')}.",
    )
    return sessao


def editar_sessao(
    sessao: SessaoTempoAtividade,
    dia: date,
    segundos: int,
    autor: Funcionario,
) -> SessaoTempoAtividade:
    antes = int(sessao.segundos or 0)
    if dia != timezone.localtime(sessao.inicio).date():
        sessao.inicio = _inicio_lancamento(dia, segundos)
    sessao.segundos = segundos
    sessao.fim = sessao.inicio + timedelta(seconds=segundos)
    sessao.save(update_fields=["inicio", "fim", "segundos"])
    _ajustar_acumulado(sessao.atividade, segundos - antes)
    registrar_evento(
        sessao.atividade,
        autor,
        TipoEventoAtividade.EDICAO,
        texto=(
            f"Corrigiu o tempo de {sessao.funcionario.nome_completo}: "
            f"{formatar_duracao(antes)} → {formatar_duracao(segundos)}."
        ),
    )
    return sessao


def excluir_sessao(sessao: SessaoTempoAtividade, autor: Funcionario) -> None:
    atividade = sessao.atividade
    segundos = int(sessao.segundos or 0)
    nome = sessao.funcionario.nome_completo
    sessao.delete()
    _ajustar_acumulado(atividade, -segundos)
    registrar_evento(
        atividade,
        autor,
        TipoEventoAtividade.EDICAO,
        texto=f"Removeu {formatar_duracao(segundos)} de tempo de {nome}.",
    )


def formatar_duracao(segundos: int) -> str:
    segundos = max(0, int(segundos or 0))
    h, resto = divmod(segundos, 3600)
    m = resto // 60
    if h and m:
        return f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    return f"{m}min"



def aparencia_atividades() -> dict:
    """Status e prioridades na ordem, nome e cor definidos no admin.

    Itens ainda não cadastrados usam o padrão do sistema.
    """
    from .models import (
        PRIORIDADE_CORES_PADRAO,
        STATUS_CORES_PADRAO,
        AparenciaPrioridade,
        AparenciaStatus,
    )

    salvos_s = {a.status: a for a in AparenciaStatus.objects.all()}
    status = []
    for i, (valor, label) in enumerate(StatusAtividade.choices):
        a = salvos_s.get(valor)
        status.append(
            {
                "valor": valor,
                "label": a.nome if a else label,
                "cor": a.cor if a else STATUS_CORES_PADRAO[valor],
                "ordem": a.ordem if a else i,
            }
        )
    salvos_p = {a.prioridade: a for a in AparenciaPrioridade.objects.all()}
    prioridades = []
    for i, (valor, label) in enumerate(PrioridadeAtividade.choices):
        a = salvos_p.get(valor)
        prioridades.append(
            {
                "valor": valor,
                "label": a.nome if a else label,
                "cor": a.cor if a else PRIORIDADE_CORES_PADRAO[valor],
                "ordem": a.ordem if a else i,
            }
        )
    status.sort(key=lambda x: x["ordem"])
    prioridades.sort(key=lambda x: x["ordem"])
    return {"status": status, "prioridades": prioridades}
