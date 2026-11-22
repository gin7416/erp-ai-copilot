select product_id, sku, product_name, category, supplier_id, unit_cost, list_price, safety_stock
from {{ ref('stg_products') }}
