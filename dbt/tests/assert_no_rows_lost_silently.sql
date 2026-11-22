-- Every raw order line is either in fct_sales or explained in audit.dq_order_line_issues.
select raw_n, kept_n, removed_n
from (
    select
        (select count(*) from {{ source('raw', 'sales_order_lines') }}) as raw_n,
        (select count(*) from {{ ref('fct_sales') }})                    as kept_n,
        (select count(*) from {{ ref('dq_order_line_issues') }})         as removed_n
)
where raw_n <> kept_n + removed_n
