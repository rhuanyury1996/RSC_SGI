from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


def _to_decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def format_brl(value) -> str:
    """Formata número no padrão brasileiro: 1.234.567,89"""
    n = _to_decimal(value)
    if n is None:
        return ""
    q = f"{n.quantize(Decimal('0.01')):,.2f}"
    return q.replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter(name="moeda")
def moeda(value, simbolo="R$"):
    """Exibe valor como moeda BR. Uso: {{ valor|moeda }} → R$ 38.055,00"""
    texto = format_brl(value)
    if not texto:
        return "—"
    prefixo = f"{simbolo} " if simbolo else ""
    return f"{prefixo}{texto}"


@register.filter(name="moeda_input")
def moeda_input(value):
    """Valor para campo de formulário (sem R$)."""
    return format_brl(value)


@register.simple_tag
def moeda_html(value, simbolo="R$"):
    """Valor com partes estilizadas (símbolo + número)."""
    texto = format_brl(value)
    if not texto:
        return mark_safe('<span class="money-empty">—</span>')
    sym = simbolo or "R$"
    return mark_safe(
        f'<span class="money"><span class="money-curr">{sym}</span>'
        f'<span class="money-amt">{texto}</span></span>'
    )
