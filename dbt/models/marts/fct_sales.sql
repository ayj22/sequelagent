-- retail: one row per order line, with the order's date, channel and store
select
    i.order_item_id,
    i.order_id,
    o.order_date,
    o.channel,
    o.store_id,
    o.customer_id,
    i.product_id,
    i.size,
    i.quantity,
    i.is_returned,
    round(i.quantity * i.unit_price, 2) as gross_revenue,
    round(i.quantity * i.unit_price * i.discount_pct, 2) as discount_amount,
    case when i.is_returned then 0 else round(i.quantity * i.unit_price * (1 - i.discount_pct), 2) end as net_revenue,
    case when i.is_returned then 0
         else round(i.quantity * (i.unit_price * (1 - i.discount_pct) - p.unit_cost), 2) end as gross_margin
from {{ ref('stg_order_items') }} i
join {{ ref('stg_orders') }} o using (order_id)
join {{ ref('stg_products') }} p using (product_id)
