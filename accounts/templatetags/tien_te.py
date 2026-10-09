from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def vnd(value):
    """Format a numeric value using Vietnamese thousands separators."""
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

    if amount == amount.to_integral_value():
        formatted = f"{int(amount):,}"
    else:
        formatted = f"{amount:,.2f}".rstrip("0").rstrip(".")
    return f"{formatted.replace(',', '.')} VND"
