select
    i.snapshot_date,
    i.warehouse_id,
    i.product_id,
    i.on_hand_qty,
    p.safety_stock,
    i.on_hand_qty < p.safety_stock as below_safety_stock
from {{ ref('stg_inventory_snapshots') }} i
join {{ ref('stg_products') }} p using (product_id)
