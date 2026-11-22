select
    trim(order_id)                        as order_id,
    cast(order_date as date)              as order_date,
    trim(customer_id)                     as customer_id,
    lower(trim(status))                   as status,
    cast(nullif(trim(ship_date), '') as date) as ship_date
from {{ source('raw', 'sales_orders') }}
