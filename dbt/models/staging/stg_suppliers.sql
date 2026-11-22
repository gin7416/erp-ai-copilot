select
    trim(supplier_id)               as supplier_id,
    trim(supplier_name)             as supplier_name,
    trim(country)                   as country,
    cast(lead_time_days as integer) as nominal_lead_time_days
from {{ source('raw', 'suppliers') }}
