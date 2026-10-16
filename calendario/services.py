from __future__ import annotations

from calendar import monthcalendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import (
    MAX_HORAS_RECUPERACAO_POR_DIA,
    Demanda,
    EventoCalendario,
    StatusDemanda,
    TipoEvento,
)

COR_ATIVIDADE = "#0ea5e9"
COR_ATIVIDADE_POR_STATUS = {
    "realizado": "#22c55e",
    "executando": "#0ea5e9",
    "em_revisao": "#f59e0b",
    "nao_iniciado": "#64748b",
}


@dataclass
class ItemCalendario:
    """Item unificado para renderizar eventos e atividades na grade."""

    titulo: str
    tipo: str
    cor: str
    inicio: datetime
    fim: datetime
    dia_inteiro: bool = True
    tipo_label: str = ""
    href: str = ""
    status: str = ""
    pessoa: str = ""
    pessoa_id: int | None = None
    editavel: bool = True
    pk: int | None = None

    def get_tipo_display(self) -> str:
        return self.tipo_label or self.tipo


def atividade_para_item(atividade, *, mostrar_pessoa: bool = False) -> ItemCalendario | None:
    """Converte AtividadeDiaria em item de calendário (usa planejado_para)."""
    dia = atividade.planejado_para or atividade.data_vencimento
    if not dia:
        return None

    if atividade.hora_inicio:
        ini = datetime.combine(dia, atividade.hora_inicio)
        fim_hora = atividade.hora_fim or atividade.hora_inicio
        fim = datetime.combine(dia, fim_hora)
        dia_inteiro = False
    else:
        ini = datetime.combine(dia, time(0, 0))
        fim = datetime.combine(dia, time(23, 59))
        dia_inteiro = True

    if timezone.is_naive(ini):
        ini = timezone.make_aware(ini, timezone.get_current_timezone())
    if timezone.is_naive(fim):
        fim = timezone.make_aware(fim, timezone.get_current_timezone())

    status = getattr(atividade, "status", "") or ""
    cor = COR_ATIVIDADE_POR_STATUS.get(status, COR_ATIVIDADE)
    status_label = (
        atividade.get_status_display()
        if hasattr(atividade, "get_status_display")
        else "Atividade"
    )
    pessoa = ""
    if mostrar_pessoa and getattr(atividade, "responsavel", None):
        pessoa = atividade.responsavel.nome_completo
    titulo = atividade.titulo
    if pessoa:
        titulo = f"{atividade.titulo} · {atividade.responsavel.nome}"
    return ItemCalendario(
        titulo=titulo,
        tipo="atividade",
        cor=cor,
        inicio=ini,
        fim=fim,
        dia_inteiro=dia_inteiro,
        tipo_label=f"Atividade · {status_label}"
        + (f" · {pessoa}" if pessoa else ""),
        href=f"{reverse('atividades')}?org=planner&data={dia.isoformat()}",
        status=status,
        pessoa=pessoa,
        pessoa_id=getattr(atividade, "responsavel_id", None),
        editavel=False,
        pk=atividade.pk,
    )


def distribuir_horas_recuperacao(
    total: Decimal,
    inicio: date,
    fim: date,
    max_por_dia: Decimal = Decimal(MAX_HORAS_RECUPERACAO_POR_DIA),
) -> list[tuple[date, Decimal]]:
    """Distribui horas no período, no máximo `max_por_dia` por dia."""
    dias: list[date] = []
    cursor = inicio
    while cursor <= fim:
        dias.append(cursor)
        cursor += timedelta(days=1)

    if not dias:
        return []

    restante = Decimal(total)
    alocacao: list[tuple[date, Decimal]] = []
    for dia in dias:
        if restante <= 0:
            break
        horas = min(max_por_dia, restante)
        alocacao.append((dia, horas))
        restante -= horas
    return alocacao


def capacidade_periodo(inicio: date, fim: date) -> Decimal:
    dias = (fim - inicio).days + 1
    if dias < 1:
        return Decimal("0")
    return Decimal(dias) * Decimal(MAX_HORAS_RECUPERACAO_POR_DIA)


def garantir_demanda_recuperacao(evento: EventoCalendario) -> list[Demanda]:
    """Cria demandas/eventos de recuperação (máx. 2h/dia) no período escolhido."""
    if evento.tipo != TipoEvento.DAY_OFF:
        return []
    if (
        evento.horas_recuperar is None
        or not evento.recuperacao_inicio
        or not evento.recuperacao_fim
    ):
        return []

    alocacao = distribuir_horas_recuperacao(
        Decimal(evento.horas_recuperar),
        evento.recuperacao_inicio,
        evento.recuperacao_fim,
    )
    if not alocacao:
        return []

    motivo_base = (
        f"Recuperação do day-off em {timezone.localtime(evento.inicio).date():%d/%m/%Y}. "
        f"{evento.motivo}"
    )

    with transaction.atomic():
        # Remove recuperações anteriores deste day-off (reagenda limpo)
        antigas = list(
            Demanda.objects.filter(evento_origem=evento).select_related("evento_agenda")
        )
        agenda_ids = [d.evento_agenda_id for d in antigas if d.evento_agenda_id]
        Demanda.objects.filter(evento_origem=evento).delete()
        if agenda_ids:
            EventoCalendario.objects.filter(
                id__in=agenda_ids,
                tipo=TipoEvento.RECUPERACAO,
            ).delete()

        criadas: list[Demanda] = []
        for dia, horas in alocacao:
            inicio = timezone.make_aware(datetime.combine(dia, time(17, 0)))
            # recupera no fim do expediente: 17h → 17h+horas (até 2h)
            fim = inicio + timedelta(hours=float(horas))
            titulo = f"Recuperar {horas}h — {evento.titulo}"

            evento_rec = EventoCalendario.objects.create(
                tipo=TipoEvento.RECUPERACAO,
                titulo=titulo,
                motivo=motivo_base,
                funcionario=evento.funcionario,
                inicio=inicio,
                fim=fim,
                dia_inteiro=False,
            )
            demanda = Demanda.objects.create(
                titulo=titulo,
                descricao=evento.motivo,
                funcionario=evento.funcionario,
                evento_origem=evento,
                evento_agenda=evento_rec,
                data_prevista=dia,
                horas=horas,
                origem_day_off=True,
                status=StatusDemanda.PENDENTE,
            )
            criadas.append(demanda)
        return criadas


def _intervalo_datas(item) -> tuple[date, date]:
    inicio = timezone.localtime(item.inicio).date()
    fim = timezone.localtime(item.fim).date()
    return inicio, fim


def montar_mes(ano: int, mes: int, itens: list) -> list[list[dict | None]]:
    """Monta a grade mensal a partir de eventos e/ou ItemCalendario."""
    por_dia: dict[date, list] = {}
    for item in itens:
        inicio, fim = _intervalo_datas(item)
        cursor = inicio
        while cursor <= fim:
            por_dia.setdefault(cursor, []).append(item)
            cursor += timedelta(days=1)

    semanas = []
    for semana in monthcalendar(ano, mes):
        linha = []
        for dia in semana:
            if dia == 0:
                linha.append(None)
            else:
                d = date(ano, mes, dia)
                dia_itens = sorted(
                    por_dia.get(d, []),
                    key=lambda e: (timezone.localtime(e.inicio), e.titulo),
                )
                linha.append(
                    {
                        "date": d,
                        "day": dia,
                        "is_today": d == timezone.localdate(),
                        "eventos": dia_itens,
                        "extra": max(0, len(dia_itens) - 3),
                        "visiveis": dia_itens[:3],
                    }
                )
        semanas.append(linha)
    return semanas


def eventos_do_dia(itens: list, dia: date) -> list:
    resultado = []
    for item in itens:
        ini, fim = _intervalo_datas(item)
        if ini <= dia <= fim:
            resultado.append(item)
    return sorted(resultado, key=lambda e: timezone.localtime(e.inicio))
