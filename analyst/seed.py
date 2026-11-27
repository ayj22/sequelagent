"""Generate a realistic but entirely fictional footwear company, Northgate Footwear Co., into the `raw` schema of a DuckDB file.

The company sells its own shoe brands two ways: retail (its stores and website) and wholesale (to other retailers). The company,
brands, products, accounts, customers and every number are invented. City and neighbourhood names are real places; customer
names are random combinations with example.com addresses. Deterministic: the same seed gives the same rows.

Behaviour built in so answers look like a real business: holiday and back-to-school peaks, weekend traffic, seasonal
categories, online share growing over time, higher online returns, loyalty members buying more, a long tail of products,
popular sizes running short in stock, wholesale orders shipping ahead of the season, short and late shipments rising in the
busy months, and marketing budgets sized to retail sales with channel-specific returns."""
from __future__ import annotations

import math
import random
from collections import Counter
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
# invented wholesale customers: name, type, region, state, relative order size
ACCOUNTS = [
    ("Whitcomb & Hale", "department store", "Northeast", "NY", 3.2), ("Marigold Department Stores", "department store", "South", "GA", 2.8),
    ("Ellery's", "department store", "Midwest", "IL", 2.3), ("Pacific Crest Mercantile", "department store", "West", "CA", 2.5),
    ("Fairbanks & Lowe", "department store", "Northeast", "PA", 1.7), ("Dunmore Brothers", "department store", "South", "TX", 1.5),
    ("Lantern Street Shoes", "specialty", "Northeast", "MA", 1.3), ("Quarry Road Footwear", "specialty", "Midwest", "OH", 1.0),
    ("Tall Pine Outfitters", "specialty", "West", "CO", 1.2), ("Saltbox Shoe Co.", "specialty", "Northeast", "ME", 0.7),
    ("Juniper & Sole", "specialty", "West", "WA", 0.9), ("Magnolia Shoe Rooms", "specialty", "South", "TN", 0.8),
    ("Two Rivers Footwear", "specialty", "Midwest", "MO", 0.7), ("Mesa Walkers", "specialty", "West", "AZ", 0.6),
    ("Gulfside Shoe Market", "specialty", "South", "FL", 0.9), ("Cobblestone & Co.", "specialty", "Northeast", "NJ", 0.8),
    ("BrightCart Marketplace", "online marketplace", "West", "CA", 2.9), ("Doorstep Goods", "online marketplace", "South", "TX", 2.0),
    ("Parcelway", "online marketplace", "Midwest", "MN", 1.4), ("ShelfHop", "online marketplace", "Northeast", "NY", 1.0),
    ("Second Season Outlet", "off-price", "South", "NC", 1.8), ("Bargain Birch", "off-price", "Midwest", "MI", 1.3),
    ("Last Pair Warehouse", "off-price", "West", "NV", 1.1), ("Thrifty Harbor", "off-price", "Northeast", "CT", 0.9),
    ("Maple Avenue Footwear", "independent", "Midwest", "WI", 0.5), ("Copper Kettle Shoes", "independent", "West", "OR", 0.4),
    ("Blue Door Footwear", "independent", "South", "SC", 0.5), ("Hearth & Heel", "independent", "Northeast", "VT", 0.3),
    ("Prairie Step", "independent", "Midwest", "IA", 0.4), ("Canyon Lane Shoes", "independent", "West", "UT", 0.4),
]
# account type -> price allowance given (low, high), share of lines shipped in full
ACCOUNT_TERMS = {"department store": (.07, .12, .90), "specialty": (.03, .06, .94), "online marketplace": (.05, .09, .92),
                 "off-price": (.22, .30, .96), "independent": (.00, .04, .93)}

WINTER = [1.5, 1.35, 0.85, 0.5, 0.35, 0.25, 0.3, 0.65, 1.15, 1.55, 1.85, 1.9]
SUMMER = [0.3, 0.4, 0.85, 1.25, 1.65, 1.9, 1.8, 1.3, 0.8, 0.45, 0.35, 0.4]
STEADY = [0.85, 0.85, 0.95, 1.0, 1.05, 1.0, 1.0, 1.15, 1.05, 1.0, 1.05, 1.1]
SCHOOL = [0.7, 0.7, 0.85, 0.9, 0.9, 0.95, 1.3, 2.0, 1.3, 0.85, 0.95, 1.2]
DRESSY = [0.8, 0.85, 1.15, 1.25, 1.2, 1.0, 0.8, 0.9, 1.0, 1.0, 1.05, 1.2]
# category -> (brand, [(model, gender, low price, high price, season)])
ASSORTMENT = {
    "Athletic": ("Kestrel", [("Tempo Runner", "Men", 95, 140, STEADY), ("Tempo Runner", "Women", 95, 140, STEADY),
                             ("Court Pro", "Men", 80, 120, SCHOOL), ("Cloudstep Trainer", "Women", 85, 125, STEADY),
                             ("Trail Dash", "Men", 105, 150, STEADY)]),
    "Casual": ("Harbor Lane", [("Court Classic", "Men", 70, 100, SCHOOL), ("Court Classic", "Women", 70, 100, SCHOOL),
                               ("Canvas Slip-On", "Women", 45, 70, SUMMER), ("Deck Shoe", "Men", 80, 115, SUMMER),
                               ("Knit Sneaker", "Women", 70, 105, STEADY)]),
    "Dress": ("Pike & Rowe", [("Cap Toe Oxford", "Men", 130, 190, DRESSY), ("Penny Loafer", "Men", 110, 165, DRESSY),
                              ("Block Heel Pump", "Women", 95, 145, DRESSY), ("Ballet Flat", "Women", 75, 110, DRESSY)]),
    "Boots": ("Ridgeline", [("Waterproof Hiker", "Men", 140, 210, WINTER), ("Waterproof Hiker", "Women", 140, 210, WINTER),
                            ("Chelsea Boot", "Men", 135, 195, WINTER), ("Chelsea Boot", "Women", 125, 185, WINTER),
                            ("Insulated Trail Boot", "Men", 155, 230, WINTER)]),
    "Sandals": ("Saltmarsh", [("River Sandal", "Men", 55, 90, SUMMER), ("Leather Slide", "Women", 40, 75, SUMMER),
                              ("Strap Sandal", "Women", 50, 85, SUMMER)]),
    "Kids": ("Tadpole", [("Light-Up Sneaker", "Kids", 40, 62, SCHOOL), ("Play Sneaker", "Kids", 35, 55, SCHOOL),
                         ("Rain Boot", "Kids", 32, 48, WINTER), ("School Mary Jane", "Kids", 38, 58, SCHOOL)]),
}
# gender -> size -> share of demand
SIZES = {"Men": {"8": .09, "9": .20, "10": .31, "11": .23, "12": .12, "13": .05},
         "Women": {"6": .12, "7": .27, "8": .32, "9": .20, "10": .09},
         "Kids": {"10C": .13, "11C": .16, "12C": .18, "13C": .18, "1Y": .15, "2Y": .12, "3Y": .08}}
# stock held relative to demand: middle sizes sell through fastest and run short, end sizes pile up
SIZE_COVER = {"Men": {"8": 1.15, "9": .9, "10": .62, "11": .85, "12": 1.2, "13": 1.8},
              "Women": {"6": 1.25, "7": .8, "8": .65, "9": 1.0, "10": 1.6},
              "Kids": {"10C": 1.2, "11C": 1.0, "12C": .85, "13C": .85, "1Y": 1.0, "2Y": 1.25, "3Y": 1.6}}
COLORS = ["Black", "Brown", "White", "Navy", "Tan", "Grey", "Olive", "Burgundy"]
FIRST = ("Olivia Liam Emma Noah Ava Ethan Sophia Mason Isabella Lucas Mia Logan Amelia James Harper Elijah Evelyn Benjamin Priya Arjun "
         "Mei Wei Sofia Mateo Camila Diego Aaliyah Jamal Hannah Samuel Grace Daniel Nora Owen Zoe Caleb Layla Isaac Ruby Julian").split()
LAST = ("Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Wilson Anderson Thomas Taylor Moore "
        "Jackson Martin Lee Perez Thompson White Harris Clark Ramirez Lewis Robinson Walker Young Patel Shah Chen Nguyen Kim Park Rivera "
        "Brooks Kelly Sanders Price Bennett Wood Barnes Ross").split()
MARKETING = {  # channel: (share of budget, return on ad spend, noise)
    "search": (.34, 4.4, .12), "social": (.29, 2.3, .22), "email": (.07, 8.6, .15), "display": (.18, 1.4, .25), "affiliate": (.12, 3.6, .18)}


def _season(day: date) -> float:
    """How busy a day is compared with an ordinary one: months, weekends and the retail calendar."""
    month = [0.78, 0.76, 0.92, 0.97, 1.02, 0.98, 1.03, 1.24, 0.99, 1.02, 1.26, 1.5][day.month - 1]
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
    return float(base - base % 5)


def _cumulative(weights: list[float]) -> list[float]:
    total, out = 0.0, []
    for w in weights:
        total += w
        out.append(total)
    return out


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def build(seed: int = 11) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)  # synthetic demo data, not security  # nosec B311
    stores = [{"store_id": i, "store_name": name, "city": city, "state": state, "region": region, "store_format": fmt,
               "opened_date": date(opened, rng.randrange(1, 13), rng.randrange(1, 28))}
              for i, (name, city, state, region, fmt, opened, _) in enumerate(STORES, 1)]
    traffic = [s[6] for s in STORES]

    products, season_of, popularity = [], [], []
    for category, (brand, models) in ASSORTMENT.items():
        for model, gender, low, high, seasonal in models:
            price = _price(rng, low, high)
            appeal = rng.lognormvariate(0, 0.35)
            for color in rng.sample(COLORS, 3):
                name = f"{brand} {model} {gender} - {color}"
                products.append({"product_id": len(products) + 1, "product_name": name, "category": category, "brand": brand,
                                 "gender": gender, "msrp": price, "wholesale_price": round(price * 0.54, 2),
                                 "unit_cost": round(price * (0.34 + rng.uniform(-0.04, 0.04)), 2)})
                season_of.append(seasonal)
                cheap = (80 / price) ** 0.35                        # inexpensive shoes sell in larger numbers
                popularity.append(appeal * cheap * rng.uniform(0.6, 1.4) * (1.45 if color in ("Black", "White") else 1.0))
    size_names = [list(SIZES[p["gender"]]) for p in products]
    size_weights = [_cumulative(list(SIZES[p["gender"]].values())) for p in products]

    states = [s[2] for s in STORES]
    customers, weight = [], []
    for i in range(1, 30001):
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
    sold: Counter = Counter()              # (month, store, product index, size) -> pairs kept, for stock levels
    days = (END - START).days + 1
    for offset in range(days):
        day = START + timedelta(days=offset)
        progress = offset / days
        volume = int(max(1, rng.gauss(300, 22) * _season(day) * (1 + 0.14 * progress)))
        online = 0.28 + 0.09 * progress + (0.07 if day.month in (11, 12) else 0)
        sale = day.month in (1, 7, 11, 12)
        buyers = rng.choices(range(len(customers)), cum_weights=cumulative_customers, k=volume)
        for buyer in buyers:
            order_id = len(orders) + 1
            channel = rng.choices(["store", "online", "bopis"], [1 - online - 0.11, online, 0.11])[0]
            store = None if channel == "online" else rng.choices(range(1, len(STORES) + 1), traffic)[0]
            orders.append({"order_id": order_id, "customer_id": buyer + 1, "order_date": day, "channel": channel, "store_id": store})
            lines = rng.choices([1, 2, 3], [72, 21, 7])[0]
            for index in rng.choices(range(len(products)), cum_weights=cumulative_products[day.month], k=lines):
                product = products[index]
                size = rng.choices(size_names[index], cum_weights=size_weights[index])[0]
                outlet = store is not None and STORES[store - 1][4] == "outlet"
                discount = rng.choices([0.0, 0.15, 0.25, 0.4], [34, 22, 30, 14] if sale else [76, 14, 8, 2])[0]
                if outlet:
                    discount = max(discount, rng.choice([0.2, 0.3]))
                returns = {"Athletic": 0.10, "Casual": 0.09, "Dress": 0.14, "Boots": 0.11, "Sandals": 0.07, "Kids": 0.06}[product["category"]]
                returns *= {"online": 1.8, "bopis": 0.9, "store": 0.65}[channel]
                quantity = rng.choices([1, 2], [95, 5])[0]
                returned = rng.random() < returns
                items.append({"order_item_id": len(items) + 1, "order_id": order_id, "product_id": product["product_id"], "size": size,
                              "quantity": quantity, "unit_price": product["msrp"], "discount_pct": discount, "is_returned": returned})
                if store is not None and not returned:
                    sold[(day.replace(day=1), store, index, size)] += quantity

    # nobody shops before signing up: a customer's signup date is never later than their first order
    for order in orders:                                    # orders are in date order
        customer = customers[order["customer_id"] - 1]
        if order["order_date"] < customer["signup_date"]:
            customer["signup_date"] = order["order_date"]

    # month-end stock for every store, product and size: demand times weeks of cover, short in the middle sizes
    inventory = []
    total_traffic = sum(traffic)
    month = START
    while month <= END:
        month_pairs = sum(n for (m, *_), n in sold.items() if m == month)
        weights = [p * s[month.month - 1] for p, s in zip(popularity, season_of)]
        total_weight = sum(weights)
        for store_id, factor in enumerate(traffic, 1):
            for index, product in enumerate(products):
                gender = product["gender"]
                for size, share in SIZES[gender].items():
                    expected = month_pairs * factor / total_traffic * weights[index] / total_weight * share
                    demand = 0.5 * expected + 0.5 * sold.get((month, store_id, index, size), 0)
                    cover = rng.lognormvariate(math.log(2.6), 0.4) * SIZE_COVER[gender][size]
                    inventory.append({"snapshot_month": month, "store_id": store_id, "product_id": product["product_id"], "size": size,
                                      "on_hand_units": max(0, int(round(demand * cover + rng.gauss(0, 0.8)))),
                                      "reorder_point": max(1, int(round(expected * 0.8)))})
        month = _next_month(month)

    # wholesale: accounts order about every 17 days, three to nine weeks ahead of the date they want the shoes
    accounts = [{"account_id": i, "account_name": name, "account_type": kind, "region": region, "state": state,
                 "customer_since": date(rng.randrange(2012, 2025), rng.randrange(1, 13), 1)}
                for i, (name, kind, region, state, _) in enumerate(ACCOUNTS, 1)]
    ahead = {m: _cumulative([p * s[(m + 1) % 12] for p, s in zip(popularity, season_of)]) for m in range(1, 13)}
    wholesale, order_number = [], 0
    for account, (_, kind, _, _, scale) in zip(accounts, ACCOUNTS):
        low, high, full_rate = ACCOUNT_TERMS[kind]
        placed = date(2024, 11, 10) + timedelta(days=rng.randrange(0, 17))
        while placed <= END:
            order_number += 1
            progress = max(0.0, (placed - START).days / days)
            requested = placed + timedelta(days=rng.randrange(21, 61))
            for index in rng.choices(range(len(products)), cum_weights=ahead[requested.month], k=rng.randrange(5, 12)):
                if not START <= requested <= END:
                    continue
                product = products[index]
                busy = requested.month in (8, 9, 10)
                late = rng.random() < (0.22 if busy else 0.09)
                delay = rng.randrange(1, 15) if late else -rng.randrange(0, 4)
                shipped_on = min(END, max(START, requested + timedelta(days=delay)))
                ordered = max(6, int(round(rng.gauss(24, 8) * scale * (1 + 0.1 * progress) / 6)) * 6)       # cases of six
                full = full_rate - (0.12 if busy and product["category"] == "Boots" else 0.03 if busy else 0)
                shipped = ordered if rng.random() < full else int(ordered * rng.choice([0, 0.5, 0.67, 0.75, 0.83]))
                wholesale.append({"order_line_id": len(wholesale) + 1, "order_id": order_number, "account_id": account["account_id"],
                                  "product_id": product["product_id"], "order_date": placed, "requested_ship_date": requested,
                                  "ship_date": shipped_on, "units_ordered": ordered, "units_shipped": shipped,
                                  "unit_price": product["wholesale_price"], "allowance_pct": round(rng.uniform(low, high), 3)})
            placed += timedelta(days=rng.randrange(12, 23))

    # weekly marketing budget: about 8% of that week's retail sales, more efficient channels getting steadier results
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
             ("inventory", inventory), ("accounts", accounts), ("wholesale_lines", wholesale), ("marketing_spend", spend)]}


DATE_COLUMNS = {"stores": ["opened_date"], "customers": ["signup_date"], "orders": ["order_date"], "inventory": ["snapshot_month"],
                "accounts": ["customer_since"], "wholesale_lines": ["order_date", "requested_ship_date", "ship_date"],
                "marketing_spend": ["week_start"]}


def write(path=WAREHOUSE_PATH, seed: int = 11) -> dict[str, int]:
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
    for table, columns in DATE_COLUMNS.items():
        for column in columns:
            con.execute(f"ALTER TABLE raw.{table} ALTER {column} TYPE DATE")
    con.close()
    return {name: len(f) for name, f in frames.items()}


if __name__ == "__main__":
    for name, n in write().items():
        print(f"raw.{name}: {n:,} rows")
