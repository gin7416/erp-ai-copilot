"""Deterministic synthetic ERP / supply-chain data for a fictional storage-device maker.

All companies, customers and suppliers are invented. A few data-quality problems are
injected on purpose (see INJECTED_ISSUES) so the dbt staging layer has real work to do.

    python -m erp_copilot.generate_data --out data/raw
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START, END = date(2025, 1, 1), date(2026, 6, 30)

INJECTED_ISSUES = {
    "duplicate_order_lines": 12,      # exact duplicate rows in sales_order_lines
    "non_positive_quantity_lines": 5,  # quantity <= 0 in sales_order_lines
    "dirty_customer_region": 4,        # region with English spelling / stray spaces
    "dirty_product_sku": 3,            # lowercase sku with surrounding spaces
}

PRODUCTS = [
    # sku, name, category, unit_cost, list_price, safety_stock, supplier_id
    ("SSD-C512-G4", "Client SSD 512GB PCIe Gen4", "SSD", 18.0, 32.0, 800, "S01"),
    ("SSD-C1T-G4", "Client SSD 1TB PCIe Gen4", "SSD", 31.0, 55.0, 900, "S01"),
    ("SSD-C2T-G4", "Client SSD 2TB PCIe Gen4", "SSD", 58.0, 99.0, 500, "S02"),
    ("SSD-C1T-G5", "Client SSD 1TB PCIe Gen5", "SSD", 52.0, 89.0, 400, "S02"),
    ("SSD-C2T-G5", "Client SSD 2TB PCIe Gen5", "SSD", 95.0, 159.0, 300, "S03"),
    ("SSD-E3T8-G5", "Enterprise SSD 3.84TB PCIe Gen5", "Enterprise SSD", 310.0, 520.0, 120, "S03"),
    ("SSD-E7T6-G5", "Enterprise SSD 7.68TB PCIe Gen5", "Enterprise SSD", 590.0, 980.0, 80, "S04"),
    ("SSD-E15T-G5", "Enterprise SSD 15.36TB PCIe Gen5", "Enterprise SSD", 1150.0, 1890.0, 40, "S04"),
    ("CTL-G4-4CH", "PCIe Gen4 4-channel SSD Controller", "Controller", 4.2, 7.5, 3000, "S05"),
    ("CTL-G4-8CH", "PCIe Gen4 8-channel SSD Controller", "Controller", 7.8, 13.0, 2500, "S05"),
    ("CTL-G5-8CH", "PCIe Gen5 8-channel SSD Controller", "Controller", 14.5, 24.0, 1800, "S06"),
    ("CTL-USB-3", "USB 3.2 Flash Controller", "Controller", 0.9, 1.8, 6000, "S06"),
    ("MC-SD-128", "SD Card 128GB", "Memory Card", 6.5, 12.0, 1500, "S07"),
    ("MC-MSD-256", "microSD Card 256GB", "Memory Card", 11.0, 21.0, 1200, "S07"),
    ("MC-MSD-512", "microSD Card 512GB", "Memory Card", 21.0, 38.0, 700, "S07"),
    ("USB-64", "USB Flash Drive 64GB", "USB Drive", 3.2, 6.5, 2000, "S08"),
    ("USB-256", "USB Flash Drive 256GB", "USB Drive", 9.5, 17.0, 1000, "S08"),
    ("EXT-SSD-1T", "Portable SSD 1TB", "Portable SSD", 38.0, 69.0, 400, "S01"),
    ("EXT-SSD-2T", "Portable SSD 2TB", "Portable SSD", 66.0, 115.0, 250, "S02"),
    ("MOD-M2-HS", "M.2 Heatsink Module", "Accessory", 2.1, 5.0, 900, "S08"),
]

SUPPLIERS = [
    # id, name, country, nominal lead time days, late probability
    ("S01", "Aurora Flash Materials", "台灣", 21, 0.08),
    ("S02", "Kestrel Semiconductor", "日本", 35, 0.10),
    ("S03", "Hanbit Memory Works", "韓國", 30, 0.12),
    ("S04", "Pacific Wafer Supply", "美國", 45, 0.15),
    ("S05", "Delta Components", "中國", 28, 0.40),   # systematically late supplier
    ("S06", "Sunrise IC Packaging", "台灣", 18, 0.05),
    ("S07", "Maple PCB Industries", "越南", 25, 0.20),
    ("S08", "Golden Bay Logistics Parts", "馬來西亞", 20, 0.10),
]

WAREHOUSES = [("W01", "北區倉", "桃園"), ("W02", "中區倉", "台中"), ("W03", "南區倉", "高雄")]

REGIONS = ["台灣", "中國", "日本", "美國", "歐洲"]
SEGMENTS = ["OEM", "通路商", "企業客戶"]
NAME_A = ["Nova", "Orion", "Zenith", "Atlas", "Vertex", "Lumen", "Polaris", "Helix", "Cobalt", "Quartz"]
NAME_B = ["Systems", "Computing", "Digital", "Devices", "Networks", "Electronics"]
DIRTY_REGION = {"日本": "Japan ", "美國": " USA", "歐洲": "Europe", "台灣": "taiwan"}


def _write(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _days(d0: date, d1: date) -> int:
    return (d1 - d0).days


def generate(out: Path, seed: int = SEED) -> dict[str, int]:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)

    # --- master data -------------------------------------------------------
    products = []
    dirty_skus = set(rng.sample(range(len(PRODUCTS)), INJECTED_ISSUES["dirty_product_sku"]))
    for i, (sku, name, cat, cost, price, safety, sup) in enumerate(PRODUCTS, start=1):
        raw_sku = f"  {sku.lower()} " if i - 1 in dirty_skus else sku
        products.append((f"P{i:03d}", raw_sku, name, cat, cost, price, safety, sup))

    suppliers = [(sid, name, country, lead) for sid, name, country, lead, _ in SUPPLIERS]
    late_prob = {sid: p for sid, *_, p in SUPPLIERS}
    lead_time = {sid: lead for sid, _, _, lead, _ in SUPPLIERS}

    customers = []
    used = set()
    for i in range(1, 31):
        while True:
            name = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
            if name not in used:
                used.add(name)
                break
        customers.append([f"C{i:03d}", name, rng.choice(REGIONS), rng.choice(SEGMENTS)])
    dirty_candidates = [c for c in customers if c[2] in DIRTY_REGION]
    for c in rng.sample(dirty_candidates, INJECTED_ISSUES["dirty_customer_region"]):
        c[2] = DIRTY_REGION[c[2]]
    customers = [tuple(c) for c in customers]

    # --- sales -------------------------------------------------------------
    weights = [1.0 if p[3] in ("SSD", "Controller", "Memory Card", "USB Drive") else 0.5 for p in products]
    cust_weight = [rng.uniform(0.3, 3.0) for _ in customers]
    orders, lines = [], []
    n_days = _days(START, END)
    for o in range(1, 1801):
        # mild growth + Q4 seasonality
        while True:
            d = START + timedelta(days=rng.randrange(n_days + 1))
            accept = 0.55 + 0.25 * (_days(START, d) / n_days) + (0.2 if d.month in (10, 11, 12) else 0)
            if rng.random() < accept:
                break
        age = _days(d, END)
        if age < 20 and rng.random() < 0.6:
            status, ship = "open", ""
        elif rng.random() < 0.05:
            status, ship = "cancelled", ""
        else:
            status, ship = "shipped", (d + timedelta(days=rng.randint(2, 12))).isoformat()
            if ship > END.isoformat():
                status, ship = "open", ""
        cust = rng.choices(customers, weights=cust_weight)[0]
        orders.append((f"SO{o:05d}", d.isoformat(), cust[0], status, ship))
        for ln, prod in enumerate(rng.sample(rng.choices(products, weights=weights, k=8), rng.randint(1, 4)), start=1):
            if prod[3] in ("Controller", "USB Drive", "Memory Card"):
                qty = rng.choice([100, 200, 250, 500, 1000, 2000])
            elif prod[3] == "Enterprise SSD":
                qty = rng.choice([4, 8, 16, 24, 32, 48])
            else:
                qty = rng.choice([20, 50, 100, 150, 200, 300])
            price = round(prod[5] * (1 - rng.uniform(0, 0.15)), 2)
            lines.append((f"SO{o:05d}", ln, prod[0], qty, price))
    # dedupe accidental duplicate (order, line) from sampling with replacement
    seen, uniq = set(), []
    for row in lines:
        if (row[0], row[2]) in seen:
            continue
        seen.add((row[0], row[2]))
        uniq.append(row)
    lines = uniq
    for idx in rng.sample(range(len(lines)), INJECTED_ISSUES["non_positive_quantity_lines"]):
        o, ln, p, _, price = lines[idx]
        lines[idx] = (o, ln, p, rng.choice([0, -50, -100]), price)
    dups = rng.sample(lines, INJECTED_ISSUES["duplicate_order_lines"])
    lines = lines + dups
    rng.shuffle(lines)

    # --- purchasing --------------------------------------------------------
    pos = []
    po_no = 0
    for prod in products:
        sup = prod[7]
        d = START + timedelta(days=rng.randint(0, 20))
        while d <= END:
            po_no += 1
            expected = d + timedelta(days=lead_time[sup])
            if expected > END + timedelta(days=10) or (d > END - timedelta(days=lead_time[sup]) and rng.random() < 0.7):
                received, status = "", "open"
            else:
                delay = rng.randint(3, 25) if rng.random() < late_prob[sup] else rng.randint(-3, 1)
                rec = expected + timedelta(days=delay)
                if rec > END:
                    received, status = "", "open"
                else:
                    received, status = rec.isoformat(), "received"
            qty = int(prod[6] * rng.uniform(0.8, 1.6) // 10 * 10)
            cost = round(prod[4] * rng.uniform(0.95, 1.05), 2)
            pos.append((f"PO{po_no:05d}", sup, prod[0], d.isoformat(), expected.isoformat(), received, qty, cost, status))
            d += timedelta(days=rng.randint(30, 60))

    # --- inventory month-end snapshots (2026-01 .. 2026-06) ---------------
    inv = []
    month_ends = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30)]
    for prod in products:
        for wid, _, _ in WAREHOUSES:
            level = prod[6] * rng.uniform(0.6, 2.2)
            for me in month_ends:
                level = max(0, level * rng.uniform(0.75, 1.25) + rng.randint(-50, 50))
                inv.append((me.isoformat(), wid, prod[0], int(level)))

    _write(out / "products.csv", ["product_id", "sku", "product_name", "category", "unit_cost", "list_price", "safety_stock", "supplier_id"], products)
    _write(out / "suppliers.csv", ["supplier_id", "supplier_name", "country", "lead_time_days"], suppliers)
    _write(out / "warehouses.csv", ["warehouse_id", "warehouse_name", "city"], WAREHOUSES)
    _write(out / "customers.csv", ["customer_id", "customer_name", "region", "segment"], customers)
    _write(out / "sales_orders.csv", ["order_id", "order_date", "customer_id", "status", "ship_date"], orders)
    _write(out / "sales_order_lines.csv", ["order_id", "line_no", "product_id", "quantity", "unit_price"], lines)
    _write(out / "purchase_orders.csv", ["po_id", "supplier_id", "product_id", "order_date", "expected_date", "received_date", "quantity", "unit_cost", "status"], pos)
    _write(out / "inventory_snapshots.csv", ["snapshot_date", "warehouse_id", "product_id", "on_hand_qty"], inv)
    return {"products": len(products), "customers": len(customers), "sales_orders": len(orders),
            "sales_order_lines": len(lines), "purchase_orders": len(pos), "inventory_snapshots": len(inv)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    print(generate(args.out, args.seed))


if __name__ == "__main__":
    main()
