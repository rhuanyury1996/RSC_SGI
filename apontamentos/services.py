from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from django.utils import timezone

from funcionarios.models import Funcionario

from .models import MarcacaoPonto, TipoMarcacao

# Fallback: 09:15–17:00 com 45 min de almoço → 7h líquidas
JORNADA_DIARIA_PADRAO_SEGUNDOS = 7 * 3600

PERIODOS = (
    ("manha", "Manhã", 6, 12, "#ff7a59"),
    ("tarde", "Tarde", 12, 18, "#3d2a26"),
    ("noite", "Noite", 18, 24, "#ffc4b0"),
    ("madrugada", "Madrugada", 0, 6, "#c9b0a8"),
)


def extrair_intervalos(marcacoes: list[MarcacaoPonto]) -> list[tuple[datetime, datetime]]:
    """Converte marcações em intervalos efetivos de trabalho."""
    itens = sorted(marcacoes, key=lambda m: m.data_hora)
    intervalos: list[tuple[datetime, datetime]] = []
    inicio: datetime | None = None

    for m in itens:
        momento = timezone.localtime(m.data_hora)

        if m.tipo == TipoMarcacao.ENTRADA:
            inicio = momento
        elif m.tipo in (TipoMarcacao.CAFE_INICIO, TipoMarcacao.ALMOCO_INICIO):
            if inicio and momento > inicio:
                intervalos.append((inicio, momento))
            inicio = None
        elif m.tipo in (TipoMarcacao.CAFE_FIM, TipoMarcacao.ALMOCO_FIM):
            inicio = momento
        elif m.tipo == TipoMarcacao.SAIDA:
            if inicio and momento > inicio:
                intervalos.append((inicio, momento))
            inicio = None

    if inicio:
        agora = timezone.localtime()
        if inicio.date() == agora.date() and agora > inicio:
            intervalos.append((inicio, agora))

    return intervalos


def segundos_trabalhados(marcacoes: list[MarcacaoPonto]) -> int:
    total = 0
    for inicio, fim in extrair_intervalos(marcacoes):
        total += int((fim - inicio).total_seconds())
    return max(total, 0)


def jornada_em_andamento(marcacoes: list[MarcacaoPonto]) -> bool:
    aberta = False
    for m in sorted(marcacoes, key=lambda item: item.data_hora):
        if m.tipo in (
            TipoMarcacao.ENTRADA,
            TipoMarcacao.CAFE_FIM,
            TipoMarcacao.ALMOCO_FIM,
        ):
            aberta = True
        elif m.tipo in (
            TipoMarcacao.SAIDA,
            TipoMarcacao.CAFE_INICIO,
            TipoMarcacao.ALMOCO_INICIO,
        ):
            aberta = False
    return aberta


def formatar_duracao(segundos: int) -> str:
    sinal = "-" if segundos < 0 else ""
    segundos = abs(int(segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, _ = divmod(resto, 60)
    return f"{sinal}{horas:02d}h{minutos:02d}"


def formatar_horas_decimal(segundos: int) -> str:
    return f"{segundos / 3600:.2f}h"


def jornada_diaria_segundos(funcionario: Funcionario | None) -> int:
    if funcionario is None:
        return JORNADA_DIARIA_PADRAO_SEGUNDOS
    return funcionario.jornada_diaria_segundos() or JORNADA_DIARIA_PADRAO_SEGUNDOS


def eh_dia_trabalho(funcionario: Funcionario | None, dia: date) -> bool:
    if funcionario is None:
        return dia.weekday() < 5
    return funcionario.trabalha_no_dia(dia)


def dias_trabalho_periodo(
    funcionario: Funcionario | None,
    inicio: date,
    fim: date,
) -> int:
    if funcionario is not None:
        return funcionario.dias_trabalho_no_periodo(inicio, fim)
    dias = 0
    cursor = inicio
    while cursor <= fim:
        if cursor.weekday() < 5:
            dias += 1
        cursor += timedelta(days=1)
    return dias


def distribuir_por_periodo(intervalos: list[tuple[datetime, datetime]]) -> dict[str, int]:
    totais = {key: 0 for key, *_ in PERIODOS}

    for inicio, fim in intervalos:
        cursor = inicio
        while cursor < fim:
            proxima_hora = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            corte = min(fim, proxima_hora)
            segundos = int((corte - cursor).total_seconds())
            hora = cursor.hour
            if 6 <= hora < 12:
                totais["manha"] += segundos
            elif 12 <= hora < 18:
                totais["tarde"] += segundos
            elif 18 <= hora < 24:
                totais["noite"] += segundos
            else:
                totais["madrugada"] += segundos
            cursor = corte

    return totais


def montar_dashboard(
    marcacoes: list[MarcacaoPonto],
    inicio: date,
    fim: date,
    funcionario: Funcionario | None = None,
) -> dict:
    por_dia: dict[date, list[MarcacaoPonto]] = defaultdict(list)
    for m in marcacoes:
        por_dia[timezone.localtime(m.data_hora).date()].append(m)

    diaria = jornada_diaria_segundos(funcionario)
    horas_por_dia_labels: list[str] = []
    horas_por_dia_valores: list[float] = []
    total_trabalhado = 0
    total_extras = 0

    cursor = inicio
    while cursor <= fim:
        itens = por_dia.get(cursor, [])
        segundos = segundos_trabalhados(itens)
        total_trabalhado += segundos
        if eh_dia_trabalho(funcionario, cursor):
            extras = max(0, segundos - diaria)
        else:
            # Fora da jornada: tudo conta como extra
            extras = segundos
        total_extras += extras
        cursor += timedelta(days=1)

    chart_inicio = max(inicio, fim - timedelta(days=13))
    cursor = chart_inicio
    while cursor <= fim:
        segundos = segundos_trabalhados(por_dia.get(cursor, []))
        horas_por_dia_labels.append(cursor.strftime("%d/%m"))
        horas_por_dia_valores.append(round(segundos / 3600, 2))
        cursor += timedelta(days=1)

    intervalos = extrair_intervalos(marcacoes)
    periodos_seg = distribuir_por_periodo(intervalos)
    periodos = []
    for key, label, _h0, _h1, cor in PERIODOS:
        periodos.append(
            {
                "key": key,
                "label": label,
                "segundos": periodos_seg[key],
                "horas": round(periodos_seg[key] / 3600, 2),
                "texto": formatar_duracao(periodos_seg[key]),
                "cor": cor,
            }
        )

    dias_uteis = dias_trabalho_periodo(funcionario, inicio, fim)
    previsto = dias_uteis * diaria
    a_quitar = max(0, previsto - total_trabalhado)

    entrada = (
        funcionario.hora_entrada.strftime("%H:%M")
        if funcionario and funcionario.hora_entrada
        else "09:15"
    )
    saida = (
        funcionario.hora_saida.strftime("%H:%M")
        if funcionario and funcionario.hora_saida
        else "17:00"
    )

    return {
        "inicio": inicio,
        "fim": fim,
        "horas_trabalhadas_seg": total_trabalhado,
        "horas_trabalhadas": formatar_duracao(total_trabalhado),
        "horas_trabalhadas_decimal": formatar_horas_decimal(total_trabalhado),
        "horas_extras_seg": total_extras,
        "horas_extras": formatar_duracao(total_extras),
        "horas_a_quitar_seg": a_quitar,
        "horas_a_quitar": formatar_duracao(a_quitar),
        "horas_previstas": formatar_duracao(previsto),
        "dias_uteis": dias_uteis,
        "jornada_diaria": formatar_duracao(diaria),
        "jornada_diaria_decimal": formatar_horas_decimal(diaria),
        "horario_padrao": f"{entrada}–{saida}",
        "resumo_jornada": (
            funcionario.resumo_jornada() if funcionario else f"Seg–Sex · {entrada}–{saida}"
        ),
        "chart_dias": {
            "labels": horas_por_dia_labels,
            "values": horas_por_dia_valores,
        },
        "chart_periodos": {
            "labels": [p["label"] for p in periodos],
            "values": [p["horas"] for p in periodos],
            "colors": [p["cor"] for p in periodos],
            "itens": periodos,
        },
        "periodo_destaque": max(periodos, key=lambda p: p["segundos"])["label"]
        if any(p["segundos"] for p in periodos)
        else "—",
    }
