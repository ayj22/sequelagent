-- the whole company in one place: retail and wholesale by day, channel and product, on the same definition of net revenue
select
    order_date as sale_date,
    'retail' as business,
    channel,
    product_id,
    coalesce(sum(quantity) filter (where not is_returned), 0) as units,
    round(sum(net_revenue), 2) as net_revenue,
    round(sum(gross_margin), 2) as gross_margin
from {{ ref('fct_sales') }}
group by 1, 2, 3, 4
union all
select
    ship_date,
    'wholesale',
    'wholesale',
    product_id,
    sum(units_shipped),
    round(sum(net_revenue), 2),
    round(sum(gross_margin), 2)
from {{ ref('fct_wholesale') }}
group by 1, 2, 3, 4
