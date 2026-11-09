from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def reais_to_cents(value: str | Decimal | int | float) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        value = Decimal(str(value))
    elif isinstance(value, str):
        cleaned = value.strip().replace("R$", "").strip()
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        value = Decimal(cleaned or "0")
    cents = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def cents_to_reais_str(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    abs_cents = abs(cents)
    whole, frac = divmod(abs_cents, 100)
    whole_str = f"{whole:,}".replace(",", ".")
    return f"{sign}R$ {whole_str},{frac:02d}"
