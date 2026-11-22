select * from {{ ref('fct_sales') }}
where abs(revenue - quantity * unit_price) > 0.01 or abs(gross_margin - (revenue - cost)) > 0.01
