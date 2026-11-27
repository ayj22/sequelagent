"""Generate a realistic but entirely fictional retailer, Cedar Ridge Outfitters, into the `raw` schema of a DuckDB file.

The company, its stores' sales, products, brands and customers are invented. City and neighbourhood names are real places;
customer names are random combinations with example.com addresses. Deterministic: the same seed gives the same rows.

Behaviour built in so answers look like a real business: holiday and back-to-school peaks, weekend traffic, seasonal
categories, online share growing over time, higher online returns (especially apparel and footwear), loyalty members buying
more, a long tail of products, and marketing budgets sized to revenue with channel-specific returns."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import duckdb
import pandas as pd

from analyst.config import WAREHOUSE_PATH

START, END = date(2025, 1, 1), date(2026, 9, 30)

# name, city, state, region, format, opened, relative traffic
STORES = [
    ("SoHo", "New York", "NY", "Northeast", "street", 2016, 1.7), ("Newbury Street", "Boston", "MA", "Northeast", "street", 2017, 1.25),
    ("King of Prussia", "King of Prussia", "PA", "Northeast", "mall", 2015, 1.15), ("Short Hills", "Millburn", "NJ", "Northeast", "mall", 2019, 1.05),
    ("Woodbury Commons", "Central Valley", "NY", "Northeast", "outlet", 2018, 1.2), ("Walnut Street", "Philadelphia", "PA", "Northeast", "street", 2021, 0.85),
    ("South Congress", "Austin", "TX", "South", "street", 2018, 1.2), ("Lenox Square", "Atlanta", "GA", "South", "mall", 2016, 1.1),
    ("The Gulch", "Nashville", "TN", "South", "street", 2022, 0.9), ("Aventura", "Miami", "FL", "South", "mall", 2017, 1.15),
    ("NorthPark", "Dallas", "TX", "South", "mall", 2015, 1.05), ("Orlando Premium", "Orlando", "FL", "South", "outlet", 2020, 1.0),
    ("Wicker Park", "Chicago", "IL", "Midwest", "street", 2016, 1.15), ("Easton Town Center", "Columbus", "OH", "Midwest", "mall", 2019, 0.85),
    ("North Loop", "Minneapolis", "MN", "Midwest", "street", 2020, 0.9), ("Somerset", "Troy", "MI", "Midwest", "mall", 2017, 0.8),
    ("Fashion Outlets", "Rosemont", "IL", "Midwest", "outlet", 2018, 0.95), ("Over-the-Rhine", "Cincinnati", "OH", "Midwest", "street", 2023, 0.7),
    ("Abbot Kinney", "Los Angeles", "CA", "West", "street", 2017, 1.35), ("Hayes Valley", "San Francisco", "CA", "West", "street", 2015, 1.2),
    ("Capitol Hill", "Seattle", "WA", "West", "street", 2018, 1.15), ("Cherry Creek", "Denver", "CO", "West", "mall", 2016, 1.1),
    ("Scottsdale Quarter", "Scottsdale", "AZ", "West", "mall", 2021, 0.85), ("Desert Hills", "Cabazon", "CA", "West", "outlet", 2019, 1.0),
]
# category -> subcategory -> (brands, model names, low price, high price, cost share, seasonal weight by month 1..12)
WINTER = [1.5, 1.35, 0.9, 0.6, 0.45, 0.35, 0.35, 0.6, 1.0, 1.35, 1.7, 1.9]
SUMMER = [0.35, 0.45, 0.8, 1.2, 1.55, 1.8, 1.75, 1.35, 0.9, 0.55, 0.45, 0.5]
STEADY = [0.85, 0.85, 0.95, 1.0, 1.05, 1.0, 1.0, 1.15, 1.05, 1.0, 1.05, 1.1]
ASSORTMENT = {
    "Footwear": {
        "Boots": (["Ridgeline", "Harbor Lane"], ["Summit Waterproof Boot", "Chelsea Boot", "Lug Sole Boot", "Insulated Trail Boot"], 119, 229, .46, WINTER),
        "Sneakers": (["Harbor Lane", "Ridgeline"], ["Court Classic", "Everyday Knit Sneaker", "Trail Runner", "Retro Runner"], 75, 150, .44, STEADY),
        "Sandals": (["Harbor Lane"], ["River Sandal", "Leather Slide", "Strap Sport Sandal"], 40, 95, .40, SUMMER),
    },
    "Apparel": {
        "Jackets": (["Northfield", "Marlow & Co"], ["Down Parka", "Waxed Field Jacket", "Rain Shell", "Quilted Liner"], 98, 298, .42, WINTER),
        "Denim": (["Marlow & Co"], ["Slim Straight Jean", "Relaxed Jean", "High Rise Jean", "Denim Trucker"], 68, 128, .39, STEADY),
        "Fleece": (["Northfield"], ["Quarter Zip Fleece", "Sherpa Pullover", "Heavyweight Hoodie"], 55, 118, .38, WINTER),
        "Tees": (["Marlow & Co", "Northfield"], ["Organic Cotton Tee", "Pocket Tee", "Performance Tee"], 22, 45, .32, SUMMER),
    },
    "Outdoor": {
        "Backpacks": (["Summitcraft"], ["Daypack 22L", "Travel Pack 38L", "Commuter Pack"], 69, 189, .45, STEADY),
        "Tents": (["Trailhaven"], ["2-Person Tent", "4-Person Family Tent", "Ultralight Shelter"], 149, 399, .52, SUMMER),
        "Drinkware": (["Trailhaven", "Summitcraft"], ["Insulated Bottle 24oz", "Camp Mug", "Wide Mouth Bottle 32oz"], 18, 42, .35, SUMMER),
    },
    "Accessories": {
        "Bags": (["Fieldnote"], ["Canvas Tote", "Weekender Duffel", "Crossbody Sling"], 38, 148, .37, STEADY),
        "Hats": (["Fieldnote", "Corvid"], ["Wool Beanie", "Washed Ball Cap", "Brim Sun Hat"], 22, 48, .30, STEADY),
        "Socks": (["Corvid"], ["Merino Hiker Sock", "Crew Sock 3-Pack", "No-Show 3-Pack"], 14, 28, .28, STEADY),
    },
}
MODEL_SEASON = {"Wool Beanie": WINTER, "Brim Sun Hat": SUMMER, "Merino Hiker Sock": WINTER, "Insulated Trail Boot": WINTER}
COLORS = ["Black", "Olive", "Navy", "Sandstone", "Slate", "Rust", "Cream", "Forest"]
FIRST = ("Olivia Liam Emma Noah Ava Ethan Sophia Mason Isabella Lucas Mia Logan Amelia James Harper Elijah Evelyn Benjamin Priya Arjun "
         "Mei Wei Sofia Mateo Camila Diego Aaliyah Jamal Hannah Samuel Grace Daniel Nora Owen Zoe Caleb Layla Isaac Ruby Julian").split()
LAST = ("Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Wilson Anderson Thomas Taylor Moore "
        "Jackson Martin Lee Perez Thompson White Harris Clark Ramirez Lewis Robinson Walker Young Patel Shah Chen Nguyen Kim Park Rivera "
        "Brooks Kelly Sanders Price Bennett Wood Barnes Ross").split()
MARKETING = {  # channel: (share of budget, return on ad spend, noise)
    "search": (.34, 4.4, .12), "social": (.29, 2.3, .22), "email": (.07, 8.6, .15), "display": (.18, 1.4, .25), "affiliate": (.12, 3.6, .18)}


def _season(day: date) -> float:
    """How busy a day is compared with an ordinary one: months, weekends and the retail calendar."""
    month = [0.78, 0.76, 0.92, 0.95, 1.02, 1.0, 1.03, 1.18, 0.97, 1.02, 1.28, 1.55][day.month - 1]
    weekday = [0.84, 0.82, 0.88, 0.93, 1.08, 1.34, 1.12][day.weekday()]
    thanksgiving = date(day.year, 11, 1) + timedelta(days=(3 - date(day.year, 11, 1).weekday()) % 7 + 21)
    offset = (day - thanksgiving).days
    event = {0: 0.55, 1: 2.9, 2: 1.8, 3: 1.35, 4: 2.1}.get(offset, 1.0)
    if day.month == 12 and 12 <= day.day <= 23:
        event *= 1.3
    if day.month == 12 and day.day == 25:
        event = 0.15
    if day.month == 7 and 1 <= day.day <= 6:
        event *= 1.18
    return month * weekday * event


def _price(rng: random.Random, low: int, high: int) -> float:
    base = rng.randrange(low, high + 1)
    return float(base - base % 5) if base > 100 else float(base)


def build(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)  # synthetic demo data, not security  # nosec B311
    stores = [{"store_id": i, "store_name": name, "city": city, "state": state, "region": region, "store_format": fmt,
               "opened_date": date(opened, rng.randrange(1, 13), rng.randrange(1, 28))}
              for i, (name, city, state, region, fmt, opened, _) in enumerate(STORES, 1)]
    traffic = [s[6] for s in STORES]

    products, season_of, popularity = [], [], []
    for category, subcategories in ASSORTMENT.items():
        for subcategory, (brands, models, low, high, cost, seasonal) in subcategories.items():
            for index, model in enumerate(models):
                brand = brands[index % len(brands)]
                price = _price(rng, low, high)
                appeal = rng.lognormvariate(0, 0.4)
                for color in rng.sample(COLORS, 4):
                    products.append({"product_id": len(products) + 1, "product_name": f"{brand} {model} - {color}",
                                     "category": category, "subcategory": subcategory, "brand": brand, "list_price": price,
                                     "unit_cost": round(price * (cost + rng.uniform(-0.03, 0.03)), 2)})
                    season_of.append(MODEL_SEASON.get(model, seasonal))
                    cheap = (60 / price) ** 0.3                        # inexpensive things sell in larger numbers
                    popularity.append(appeal * cheap * rng.uniform(0.6, 1.4) * (1.4 if color in ("Black", "Navy") else 1.0))

    states = [s[2] for s in STORES]
    customers, weight = [], []
    for i in range(1, 24001):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        tier = rng.choices(["none", "silver", "gold"], [62, 27, 11])[0]
        segment = rng.choices(["value", "core", "premium"], [38, 45, 17])[0]
        customers.append({"customer_id": i, "full_name": f"{first} {last}", "email": f"{first}.{last}{i}@example.com".lower(),
                          "state": rng.choices(states, traffic)[0], "segment": segment, "loyalty_tier": tier,
                          "signup_date": date(2021, 3, 1) + timedelta(days=int((END - date(2021, 3, 1)).days * rng.random() ** 0.85))})
        weight.append({"none": 1.0, "silver": 2.1, "gold": 4.2}[tier] * rng.lognormvariate(0, 0.5))
    cumulative_customers = _cumulative(weight)
    cumulative_products = {m: _cumulative([p * s[m - 1] for p, s in zip(popularity, season_of)]) for m in range(1, 13)}

    orders, items = [], []
    days = (END - START).days + 1
    for offset in range(days):
        day = START + timedelta(days=offset)
        progress = offset / days
        volume = int(max(1, rng.gauss(205, 16) * _season(day) * (1 + 0.17 * progress)))
        online = 0.29 + 0.09 * progress + (0.07 if day.month in (11, 12) else 0)
        sale = day.month in (11, 12) or (day.month, day.day <= 7) in ((7, True),) or day.month == 1
        buyers = rng.choices(range(len(customers)), cum_weights=cumulative_customers, k=volume)
        for buyer in buyers:
            order_id = len(orders) + 1
            channel = rng.choices(["store", "online", "bopis"], [1 - online - 0.11, online, 0.11])[0]
            store = None if channel == "online" else rng.choices(range(1, len(STORES) + 1), traffic)[0]
            orders.append({"order_id": order_id, "customer_id": buyer + 1, "order_date": day, "channel": channel, "store_id": store})
            lines = rng.choices([1, 2, 3, 4, 5], [48, 28, 14, 7, 3])[0]
            for product_index in rng.choices(range(len(products)), cum_weights=cumulative_products[day.month], k=lines):
                product = products[product_index]
                outlet = store is not None and STORES[store - 1][4] == "outlet"
                discount = rng.choices([0.0, 0.15, 0.25, 0.4], [34, 22, 30, 14] if sale else [76, 14, 8, 2])[0]
                if outlet:
                    discount = max(discount, rng.choice([0.2, 0.3]))
                returns = {"Apparel": 0.11, "Footwear": 0.10, "Outdoor": 0.05, "Accessories": 0.04}[product["category"]]
                returns *= {"online": 1.75, "bopis": 0.9, "store": 0.65}[channel]
                items.append({"order_item_id": len(items) + 1, "order_id": order_id, "product_id": product["product_id"],
                              "quantity": rng.choices([1, 2, 3], [87, 11, 2])[0], "unit_price": product["list_price"],
                              "discount_pct": discount, "is_returned": rng.random() < returns})

    inventory = []
    month = date(2025, 1, 1)
    total_popularity = sum(popularity)
    while month <= END:
        for store_id, factor in enumerate(traffic, 1):
            for product, pop, seasonal in zip(products, popularity, season_of):
                monthly_demand = 330 * factor * pop * seasonal[month.month - 1] / total_popularity * 4
                cover = rng.lognormvariate(math.log(1.7), 0.55)
                inventory.append({"snapshot_month": month, "store_id": store_id, "product_id": product["product_id"],
                                  "on_hand_units": max(0, int(round(monthly_demand * cover + rng.gauss(0, 1.2)))),
                                  "reorder_point": max(2, int(round(monthly_demand * 0.75)))})
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)

    # weekly marketing budget: about 8% of that week's sales, more efficient channels getting steadier results
    order_day = {o["order_id"]: o["order_date"] for o in orders}
    weekly: dict[date, float] = {}
    for line in items:
        day = order_day[line["order_id"]]
        monday = day - timedelta(days=day.weekday())
        weekly[monday] = weekly.get(monday, 0) + line["quantity"] * line["unit_price"] * (1 - line["discount_pct"])
    spend = []
    for monday in sorted(w for w in weekly if w >= START):
        budget = weekly[monday] * 0.081 * rng.uniform(0.9, 1.1)
        for channel, (share, roas, noise) in MARKETING.items():
            amount = round(budget * share * rng.uniform(1 - noise, 1 + noise), 2)
            lift = 1.18 if monday.month in (11, 12) else 1.0
            spend.append({"week_start": monday, "marketing_channel": channel, "spend": amount,
                          "attributed_revenue": round(amount * roas * lift * rng.uniform(1 - noise, 1 + noise), 2)})
    return {name: pd.DataFrame(rows) for name, rows in
            [("stores", stores), ("products", products), ("customers", customers), ("orders", orders), ("order_items", items),
             ("inventory", inventory), ("marketing_spend", spend)]}


def _cumulative(weights: list[float]) -> list[float]:
    total, out = 0.0, []
    for w in weights:
        total += w
        out.append(total)
    return out


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
        con.execute(f"CREATE TABLE raw.{name} AS SELECT * FROM frame")  # names are the constants above  # nosec B608
        con.unregister("frame")
    for table, column in [("stores", "opened_date"), ("customers", "signup_date"), ("orders", "order_date"),
                          ("inventory", "snapshot_month"), ("marketing_spend", "week_start")]:
        con.execute(f"ALTER TABLE raw.{table} ALTER {column} TYPE DATE")
    con.close()
    return {name: len(f) for name, f in frames.items()}


if __name__ == "__main__":
    for name, n in write().items():
        print(f"raw.{name}: {n:,} rows")
