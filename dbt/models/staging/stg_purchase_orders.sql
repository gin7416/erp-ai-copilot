select
    trim(po_id)                                   as po_id,
    trim(supplier_id)                             as supplier_id,
    trim(product_id)                              as product_id,
    cast(order_date as date)                      as order_date,
    cast(expected_date as date)                   as expected_date,
    cast(nullif(trim(received_date), '') as date) as received_date,
    cast(quantity as integer)                     as quantity,
    cast(unit_cost as decimal(12, 2))             as unit_cost,
    lower(trim(status))                           as status
from {{ source('raw', 'purchase_orders') }}
