select
    trim(product_id)                    as product_id,
    upper(trim(sku))                    as sku,          -- raw has lowercase / padded SKUs
    trim(product_name)                  as product_name,
    trim(category)                      as category,
    cast(unit_cost as decimal(12, 2))   as unit_cost,
    cast(list_price as decimal(12, 2))  as list_price,
    cast(safety_stock as integer)       as safety_stock,
    trim(supplier_id)                   as supplier_id
from {{ source('raw', 'products') }}
