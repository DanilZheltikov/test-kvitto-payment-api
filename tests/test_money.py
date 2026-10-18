import pytest

from app.services.money import apply_discount, build_schedule

BASIC_PRICE = 990_000
STANDARD_PRICE = 1_990_000
PREMIUM_PRICE = 2_990_000
DISCOUNT_PERCENT = 10

EXPECTED_BASIC_AMOUNT = 891_000
EXPECTED_BASIC_DISCOUNT = 99_000
EXPECTED_STANDARD_AMOUNT = 1_791_000
EXPECTED_STANDARD_DISCOUNT = 199_000
EXPECTED_PREMIUM_AMOUNT = 2_691_000
EXPECTED_PREMIUM_DISCOUNT = 299_000

EXPECTED_SCHEDULE_3_MONTHS_WITH_REMAINDER = [663_334, 663_333, 663_333]
EXPECTED_SCHEDULE_6_MONTHS_WITH_REMAINDER = [331_667] * 4 + [331_666] * 2
EXPECTED_SCHEDULE_12_MONTHS_WITH_REMAINDER = [165_834] * 4 + [165_833] * 8

EXPECTED_SCHEDULE_3_MONTHS_AFTER_DISCOUNT = [597_000] * 3
EXPECTED_SCHEDULE_6_MONTHS_AFTER_DISCOUNT = [298_500] * 6
EXPECTED_SCHEDULE_12_MONTHS_AFTER_DISCOUNT = [149_250] * 12

EXPECTED_SCHEDULE_3_MONTHS_SMALL_AMOUNT = [1, 1, 0]
EXPECTED_SCHEDULE_6_MONTHS_SMALL_AMOUNT = [1, 1, 0, 0, 0, 0]
EXPECTED_SCHEDULE_12_MONTHS_SMALL_AMOUNT = [1, 1] + [0] * 10
EXPECTED_SCHEDULE_12_MONTHS_ZERO_AMOUNT = [0] * 12


@pytest.mark.parametrize(
    ("price", "discount_percent", "expected_amount", "expected_discount"),
    [
        pytest.param(
            BASIC_PRICE, 0, BASIC_PRICE, 0,
            id="basic-without-discount",
        ),
        pytest.param(
            STANDARD_PRICE, 0, STANDARD_PRICE, 0,
            id="standard-without-discount",
        ),
        pytest.param(
            PREMIUM_PRICE, 0, PREMIUM_PRICE, 0,
            id="premium-without-discount",
        ),
        pytest.param(
            BASIC_PRICE, DISCOUNT_PERCENT,
            EXPECTED_BASIC_AMOUNT, EXPECTED_BASIC_DISCOUNT,
            id="basic-ten-percent",
        ),
        pytest.param(
            STANDARD_PRICE, DISCOUNT_PERCENT,
            EXPECTED_STANDARD_AMOUNT, EXPECTED_STANDARD_DISCOUNT,
            id="standard-ten-percent",
        ),
        pytest.param(
            PREMIUM_PRICE, DISCOUNT_PERCENT,
            EXPECTED_PREMIUM_AMOUNT, EXPECTED_PREMIUM_DISCOUNT,
            id="premium-ten-percent",
        ),
        pytest.param(
            1, DISCOUNT_PERCENT, 1, 0,
            id="discount-less-than-one-kopeck",
        ),
        pytest.param(
            19, DISCOUNT_PERCENT, 18, 1,
            id="round-discount-down-not-to-nearest",
        ),
        pytest.param(
            1_009, DISCOUNT_PERCENT, 909, 100,
            id="round-discount-down",
        ),
    ],
)
def test_apply_discount(
    price: int,
    discount_percent: int,
    expected_amount: int,
    expected_discount: int,
) -> None:
    amount, discount = apply_discount(price, discount_percent)

    assert amount == expected_amount
    assert discount == expected_discount
    assert amount + discount == price
    assert type(amount) is int
    assert type(discount) is int


@pytest.mark.parametrize(
    ("amount", "months", "expected_schedule"),
    [
        pytest.param(
            STANDARD_PRICE, 3, EXPECTED_SCHEDULE_3_MONTHS_WITH_REMAINDER,
            id="remainder-three-months",
        ),
        pytest.param(
            STANDARD_PRICE, 6, EXPECTED_SCHEDULE_6_MONTHS_WITH_REMAINDER,
            id="remainder-six-months",
        ),
        pytest.param(
            STANDARD_PRICE, 12, EXPECTED_SCHEDULE_12_MONTHS_WITH_REMAINDER,
            id="remainder-twelve-months",
        ),
        pytest.param(
            EXPECTED_STANDARD_AMOUNT, 3,
            EXPECTED_SCHEDULE_3_MONTHS_AFTER_DISCOUNT,
            id="equal-three-months-after-discount",
        ),
        pytest.param(
            EXPECTED_STANDARD_AMOUNT, 6,
            EXPECTED_SCHEDULE_6_MONTHS_AFTER_DISCOUNT,
            id="equal-six-months-after-discount",
        ),
        pytest.param(
            EXPECTED_STANDARD_AMOUNT, 12,
            EXPECTED_SCHEDULE_12_MONTHS_AFTER_DISCOUNT,
            id="equal-twelve-months-after-discount",
        ),
        pytest.param(
            2, 3, EXPECTED_SCHEDULE_3_MONTHS_SMALL_AMOUNT,
            id="small-amount-three-months",
        ),
        pytest.param(
            2, 6, EXPECTED_SCHEDULE_6_MONTHS_SMALL_AMOUNT,
            id="small-amount-six-months",
        ),
        pytest.param(
            2, 12, EXPECTED_SCHEDULE_12_MONTHS_SMALL_AMOUNT,
            id="small-amount-twelve-months",
        ),
        pytest.param(
            0, 12, EXPECTED_SCHEDULE_12_MONTHS_ZERO_AMOUNT,
            id="zero-amount",
        ),
    ],
)
def test_build_schedule(
    amount: int,
    months: int,
    expected_schedule: list[int],
) -> None:
    schedule = build_schedule(amount, months)

    assert schedule == expected_schedule
    assert len(schedule) == months
    assert sum(schedule) == amount
    assert all(type(payment) is int for payment in schedule)
