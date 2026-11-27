-- month-end stock by store, product and size, with the pairs that store sold that month (store and pick-up orders)
with sold as (
    select date_trunc('month', order_date)::date as snapshot_month, store_id, product_id, size,
           sum(quantity) filter (where not is_returned) as units_sold
    from {{ ref('fct_sales') }}
    where store_id is not null
    group by 1, 2, 3, 4
)
select
    i.snapshot_month,
    i.store_id,
    i.product_id,
    i.size,
    i.on_hand_units,
    i.reorder_point,
    coalesce(s.units_sold, 0) as units_sold,
    round(coalesce(s.units_sold, 0) * 7.0 / date_part('day', last_day(i.snapshot_month)), 4) as weekly_units_sold
from {{ ref('stg_inventory') }} i
left join sold s using (snapshot_month, store_id, product_id, size)
