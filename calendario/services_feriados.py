"""Cadastro de feriados no calendário para crédito automático de jornada."""

from __future__ import annotations

from datetime import date, datetime, time

from django.utils import timezone

from apontamentos.services import feriados_nacionais_nomeados
from funcionarios.models import Funcionario

from .models import EventoCalendario, StatusEvento, TipoEvento


def _bounds_dia(dia: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(dia, time.min), tz)
    fim = timezone.make_aware(datetime.combine(dia, time.max.replace(microsecond=0)), tz)
    return inicio, fim


def cadastrar_feriados_ano(ano: int) -> dict[str, int]:
    """
    Garante um evento tipo Feriado (dia inteiro) por colaborador ativo
    para cada feriado nacional do ano. Idempotente.
    """
    funcionarios = list(
        Funcionario.objects.filter(ativo=True).order_by("nome", "sobrenome")
    )
    if not funcionarios:
        return {"funcionarios": 0, "feriados": 0, "criados": 0, "existentes": 0}

    feriados = feriados_nacionais_nomeados(ano)
    criados = 0
    existentes = 0

    for dia, nome in sorted(feriados.items()):
        inicio, fim = _bounds_dia(dia)
        titulo = f"Feriado · {nome}"
        for func in funcionarios:
            ja_existe = EventoCalendario.objects.filter(
                funcionario=func,
                tipo=TipoEvento.FERIADO,
                inicio__date=dia,
            ).exists()
            if ja_existe:
                existentes += 1
                continue
            EventoCalendario.objects.create(
                funcionario=func,
                tipo=TipoEvento.FERIADO,
                titulo=titulo,
                motivo=(
                    f"Feriado nacional — jornada creditada automaticamente ({nome})."
                ),
                inicio=inicio,
                fim=fim,
                dia_inteiro=True,
                status=StatusEvento.CONFIRMADO,
            )
            criados += 1

    return {
        "funcionarios": len(funcionarios),
        "feriados": len(feriados),
        "criados": criados,
        "existentes": existentes,
    }
