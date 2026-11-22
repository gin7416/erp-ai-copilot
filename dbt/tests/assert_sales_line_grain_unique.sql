-- fct_sales must have one row per (order_id, line_no) after de-duplication.
select order_id, line_no, count(*) as n
from {{ ref('fct_sales') }}
group by 1, 2
having count(*) > 1
