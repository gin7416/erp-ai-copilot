-- Region values arrive with mixed spellings ("Japan ", " USA", "taiwan"); map them to the Chinese canonical form.
select
    trim(customer_id)   as customer_id,
    trim(customer_name) as customer_name,
    case lower(trim(region))
        when 'japan'  then '日本'
        when 'usa'    then '美國'
        when 'europe' then '歐洲'
        when 'taiwan' then '台灣'
        when 'china'  then '中國'
        else trim(region)
    end                 as region,
    trim(segment)       as segment
from {{ source('raw', 'customers') }}
