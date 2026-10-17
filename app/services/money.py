def apply_discount(price: int, discount_percent: int) -> tuple[int, int]:
    """Return (amount, discount) for a validated price and percentage."""
    discount = price * discount_percent // 100
    return price - discount, discount


def build_schedule(amount: int, months: int) -> list[int]:
    """Distribute validated kopecks across a validated positive month count."""
    base, remainder = divmod(amount, months)
    return [base + (index < remainder) for index in range(months)]
