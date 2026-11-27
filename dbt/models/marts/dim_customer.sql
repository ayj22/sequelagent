-- personal data (name, email) stops here: it is never published
select customer_id, state, segment, loyalty_tier, signup_date
from {{ ref('stg_customers') }}
