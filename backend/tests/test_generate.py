from collections import Counter
from datetime import date

from data.generate import BAD_SUPPLIER, CATEGORIES, REGIONS, SUPPLIERS, generate


def _index(ds):
    products = {p[0]: p for p in ds.products}
    orders = {o[0]: o for o in ds.orders}
    return products, orders


def test_same_seed_gives_identical_data():
    a, b = generate(seed=42), generate(seed=42)
    assert a.orders == b.orders
    assert a.order_items == b.order_items
    assert a.refunds == b.refunds


def test_sizes(dataset):
    assert len(dataset.customers) == 2000
    assert len(dataset.products) == 120
    assert 9_900 <= len(dataset.orders) <= 10_100
    assert Counter(p[2] for p in dataset.products) == {c: 20 for c in CATEGORIES}
    assert Counter(p[3] for p in dataset.products) == {s: 15 for s in SUPPLIERS}
    assert {c[3] for c in dataset.customers} == set(REGIONS)


def test_values_are_consistent(dataset):
    _products, orders = _index(dataset)
    assert len({c[2] for c in dataset.customers}) == len(dataset.customers)  # unique emails
    assert all(c[2].endswith("@example.com") for c in dataset.customers)
    assert all(date(2024, 1, 1) <= o[2] <= date(2025, 12, 31) for o in orders.values())
    items = {i[0]: i for i in dataset.order_items}
    for refund in dataset.refunds:
        item = items[refund[1]]
        assert orders[item[1]][5] == "completed"          # only completed orders are refunded
        assert refund[4] == round(item[4] * item[3], 2)   # full refund of the line
        assert refund[2] > orders[item[1]][2]             # refund after the order


def test_t1_holiday_spike(dataset):
    per_month = Counter((o[2].year, o[2].month) for o in dataset.orders)
    holiday = [n for (_, m), n in per_month.items() if m in (11, 12)]
    other = [n for (_, m), n in per_month.items() if m not in (11, 12)]
    assert (sum(holiday) / len(holiday)) >= 1.5 * (sum(other) / len(other))


def test_t2_bad_supplier_refund_rate(dataset):
    products, orders = _index(dataset)
    refunded = {r[1] for r in dataset.refunds}
    completed = [i for i in dataset.order_items if orders[i[1]][5] == "completed"]
    sold = Counter(products[i[2]][3] for i in completed)
    returned = Counter(products[i[2]][3] for i in completed if i[0] in refunded)
    rate = {s: returned[s] / sold[s] for s in sold}
    others = [r for s, r in rate.items() if s != BAD_SUPPLIER]
    assert rate[BAD_SUPPLIER] >= 2.5 * (sum(others) / len(others))


def test_t3_march_north_electronics_drop(dataset):
    products, orders = _index(dataset)

    def electronics_orders(in_region, year, month):
        return len({
            i[1] for i in dataset.order_items
            if products[i[2]][2] == "Electronics"
            and in_region(orders[i[1]][4])
            and (orders[i[1]][2].year, orders[i[1]][2].month) == (year, month)
        })

    def ratio(in_region):
        baseline = (electronics_orders(in_region, 2025, 2) + electronics_orders(in_region, 2025, 4)) / 2
        return electronics_orders(in_region, 2025, 3) / baseline

    assert ratio(lambda r: r == "North") <= 0.40     # North Electronics collapsed in March
    assert ratio(lambda r: r != "North") >= 0.80     # other regions were normal
