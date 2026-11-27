-- wholesale: one row per order line shipped to an account; money is earned on the units that shipped
select
    w.order_line_id,
    w.order_id,
    w.account_id,
    w.product_id,
    w.order_date,
    w.requested_ship_date,
    w.ship_date,
    w.units_ordered,
    w.units_shipped,
    round(w.units_shipped * w.unit_price, 2) as gross_revenue,
    round(w.units_shipped * w.unit_price * w.allowance_pct, 2) as allowance_amount,
    round(w.units_shipped * w.unit_price * (1 - w.allowance_pct), 2) as net_revenue,
    round(w.units_shipped * (w.unit_price * (1 - w.allowance_pct) - p.unit_cost), 2) as gross_margin
from {{ ref('stg_wholesale_lines') }} w
join {{ ref('stg_products') }} p using (product_id)
