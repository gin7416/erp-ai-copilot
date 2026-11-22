select warehouse_id, warehouse_name, city from {{ ref('stg_warehouses') }}
