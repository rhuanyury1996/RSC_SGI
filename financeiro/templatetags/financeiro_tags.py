from django import template

from ledger.money import cents_to_reais_str

register = template.Library()


@register.filter
def money(value) -> str:
    try:
        return cents_to_reais_str(int(value))
    except (TypeError, ValueError):
        return "—"


@register.filter
def absval(value):
    try:
        return abs(value)
    except TypeError:
        return value


@register.filter
def get_item(d, key):
    try:
        return d.get(key, 0)
    except AttributeError:
        return 0
