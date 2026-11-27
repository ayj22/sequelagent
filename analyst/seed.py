"""Generate a synthetic retail business (no real people or companies) into the `raw` schema of a DuckDB file.

Deterministic: the same seed always produces the same rows, so evaluation answers are stable."""
from __future__ import annotations

import random
from datetime import date, timedelta

import duckdb
import pandas as pd

from analyst.config import WAREHOUSE_PATH

START, END = date(2025, 1, 1), date(2026, 9, 30)
REGIONS = {"Northeast": ["NY", "NJ", "MA", "PA"], "South": ["TX", "GA", "FL", "TN"],
           "Midwest": ["IL", "OH", "MI", "MN"], "West": ["CA", "WA", "CO", "AZ"]}
CATALOG = {"Footwear": (["Sneakers", "Boots", "Sandals", "Loafers"], 45, 160),
           "Apparel": (["Jackets", "Denim", "Tees", "Hoodies"], 18, 140),
           "Accessories": (["Bags", "Hats", "Belts", "Socks"], 8, 90),
           "Outdoor": (["Backpacks", "Tents", "Bottles", "Jackets Pro"], 15, 220)}
BRANDS = ["Northpeak", "Lumen", "Harbor & Co", "Vantage", "Meadow", "Kite"]
CHANNELS = ["store", "online", "bopis"]
MARKETING = ["search", "social", "email", "display", "affiliate"]


def build(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    stores = []
    for i in range(1, 25):
        region = list(REGIONS)[(i - 1) % 4]
        stores.append({"store_id": i, "store_name": f"{region} Store {(i - 1) // 4 + 1}", "region": region,
                       "state": rng.choice(REGIONS[region]), "store_format": rng.choice(["mall", "street", "outlet"]),
                       "opened_date": date(2015, 1, 1) + timedelta(days=rng.randrange(3200))})
    products = []
    for i in range(1, 121):
        category = list(CATALOG)[(i - 1) % 4]
        subs, low, high = CATALOG[category]
        price = round(rng.uniform(low, high), 2)
        sub = rng.choice(subs)
        brand = rng.choice(BRANDS)
        products.append({"product_id": i, "product_name": f"{brand} {sub} {i:03d}", "category": category, "subcategory": sub,
                         "brand": brand, "list_price": price, "unit_cost": round(price * rng.uniform(0.38, 0.62), 2)})
    states = [s for v in REGIONS.values() for s in v]
    customers = [{"customer_id": i, "full_name": f"Customer {i}", "email": f"customer{i}@example.com", "state": rng.choice(states),
                  "segment": rng.choices(["value", "core", "premium"], [45, 40, 15])[0],
                  "loyalty_tier": rng.choices(["none", "silver", "gold"], [55, 30, 15])[0],
                  "signup_date": date(2022, 1, 1) + timedelta(days=rng.randrange((END - date(2022, 1, 1)).days))}
                 for i in range(1, 4001)]

    orders, items = [], []
    days = (END - START).days + 1
    order_id = item_id = 0
    popularity = [rng.paretovariate(1.6) for _ in products]
    for offset in range(days):
        day = START + timedelta(days=offset)
        season = {11: 1.5, 12: 1.8, 7: 1.15, 1: 0.8, 2: 0.8}.get(day.month, 1.0)
        growth = 1 + 0.18 * offset / days
        for _ in range(int(rng.gauss(55, 6) * season * growth * (1.25 if day.weekday() >= 5 else 1))):
            order_id += 1
            channel = rng.choices(CHANNELS, [55, 33, 12])[0]
            customer = rng.choice(customers)
            orders.append({"order_id": order_id, "customer_id": customer["customer_id"], "order_date": day, "channel": channel,
                           "store_id": None if channel == "online" else rng.randrange(1, 25)})
            for _ in range(rng.choices([1, 2, 3, 4], [50, 28, 15, 7])[0]):
                item_id += 1
                p = rng.choices(products, popularity)[0]
                promo = 0.25 if day.month in (11, 12) else 0.1
                discount = rng.choices([0, promo], [70, 30])[0]
                qty = rng.choices([1, 2, 3], [78, 17, 5])[0]
                items.append({"order_item_id": item_id, "order_id": order_id, "product_id": p["product_id"], "quantity": qty,
                              "unit_price": p["list_price"], "discount_pct": discount,
                              "is_returned": rng.random() < (0.14 if channel == "online" else 0.06)})
    inventory = []
    month = date(2025, 1, 1)
    while month <= END:
        for s in stores:
            for p in products:
                on_hand = max(0, int(rng.gauss(22, 12) * min(2.0, popularity[p["product_id"] - 1])))
                inventory.append({"snapshot_month": month, "store_id": s["store_id"], "product_id": p["product_id"],
                                  "on_hand_units": on_hand, "reorder_point": 8})
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    spend = []
    week = date(2025, 1, 6)
    while week <= END:
        for ch in MARKETING:
            amount = round(rng.uniform(2000, 12000) * (1.5 if week.month in (11, 12) else 1), 2)
            spend.append({"week_start": week, "marketing_channel": ch, "spend": amount,
                          "attributed_revenue": round(amount * rng.uniform(1.2, {"email": 6.5, "search": 4.5}.get(ch, 3.2)), 2)})
        week += timedelta(days=7)
    return {name: pd.DataFrame(rows) for name, rows in
            [("stores", stores), ("products", products), ("customers", customers), ("orders", orders), ("order_items", items),
             ("inventory", inventory), ("marketing_spend", spend)]}


def write(path=WAREHOUSE_PATH, seed: int = 7) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    frames = build(seed)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA raw")
    for name, frame in frames.items():
        if name == "orders":
            frame = frame.astype({"store_id": "Int64"})
        con.register("frame", frame)
        con.execute(f"CREATE TABLE raw.{name} AS SELECT * FROM frame")
        con.unregister("frame")
    for table, column in [("stores", "opened_date"), ("customers", "signup_date"), ("orders", "order_date"),
                          ("inventory", "snapshot_month"), ("marketing_spend", "week_start")]:
        con.execute(f"ALTER TABLE raw.{table} ALTER {column} TYPE DATE")
    con.close()
    return {name: len(f) for name, f in frames.items()}


if __name__ == "__main__":
    for name, n in write().items():
        print(f"raw.{name}: {n:,} rows")
