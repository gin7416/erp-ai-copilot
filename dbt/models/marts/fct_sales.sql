select
    l.order_id,
    l.line_no,
    o.order_date,
    cast(date_trunc('month', o.order_date) as date)   as order_month,
    o.ship_date,
    o.status,
    o.customer_id,
    l.product_id,
    l.quantity,
    l.unit_price,
    cast(l.quantity * l.unit_price as decimal(14, 2))                    as revenue,
    cast(l.quantity * p.unit_cost as decimal(14, 2))                     as cost,
    cast(l.quantity * (l.unit_price - p.unit_cost) as decimal(14, 2))    as gross_margin
from {{ ref('stg_sales_order_lines') }} l
join {{ ref('stg_sales_orders') }} o using (order_id)
join {{ ref('stg_products') }} p using (product_id)
