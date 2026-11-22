select
    cast(snapshot_date as date)  as snapshot_date,
    trim(warehouse_id)           as warehouse_id,
    trim(product_id)             as product_id,
    cast(on_hand_qty as integer) as on_hand_qty
from {{ source('raw', 'inventory_snapshots') }}
