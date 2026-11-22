-- Rows removed by stg_sales_order_lines, with the reason, so data loss is visible and testable.
with raw_lines as (
    select *, row_number() over (partition by order_id, line_no, product_id, quantity, unit_price) as copy_no
    from {{ source('raw', 'sales_order_lines') }}
)
select order_id, line_no, product_id, quantity, unit_price, 'duplicate_row' as issue
from raw_lines where copy_no > 1
union all
select order_id, line_no, product_id, quantity, unit_price, 'non_positive_quantity' as issue
from raw_lines where copy_no = 1 and cast(quantity as integer) <= 0
