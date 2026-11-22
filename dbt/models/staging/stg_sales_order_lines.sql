-- Removes exact duplicate rows and lines with non-positive quantity (both logged in audit.dq_order_line_issues).
with typed as (
    select distinct
        trim(order_id)                     as order_id,
        cast(line_no as integer)           as line_no,
        trim(product_id)                   as product_id,
        cast(quantity as integer)          as quantity,
        cast(unit_price as decimal(12, 2)) as unit_price
    from {{ source('raw', 'sales_order_lines') }}
)
select * from typed where quantity > 0
