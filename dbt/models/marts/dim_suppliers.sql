select supplier_id, supplier_name, country, nominal_lead_time_days from {{ ref('stg_suppliers') }}
