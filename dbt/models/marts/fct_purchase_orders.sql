select
    po_id,
    supplier_id,
    product_id,
    order_date,
    expected_date,
    received_date,
    quantity,
    unit_cost,
    cast(quantity * unit_cost as decimal(14, 2))                          as amount,
    status,
    case when received_date is not null then received_date - order_date end    as actual_lead_time_days,
    case when received_date is not null then received_date - expected_date end as days_late,
    coalesce(received_date > expected_date, false)                        as is_late
from {{ ref('stg_purchase_orders') }}
