select trim(warehouse_id) as warehouse_id, trim(warehouse_name) as warehouse_name, trim(city) as city
from {{ source('raw', 'warehouses') }}
