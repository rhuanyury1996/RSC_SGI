from datetime import datetime

from django import template
from django.utils import timezone

register = template.Library()


@register.filter(name="momento")
def momento(valor) -> str:
    """ISO gravado no histórico → "05/11/2026 01:41" no fuso do SGI."""
    if not valor:
        return "—"
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return valor
    if timezone.is_aware(valor):
        valor = timezone.localtime(valor)
    return valor.strftime("%d/%m/%Y %H:%M")
