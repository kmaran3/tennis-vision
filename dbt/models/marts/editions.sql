select tour,edition_id,season,any_value(event) as event,any_value(surface) as surface,
min(observed_date) as start_date, max(observed_date) as last_observed_date,count(*) as matches,
'unavailable' as venue_status,'Venue history has not yet been verified for this edition' as unavailable_reason
from {{ref('matches')}} where season>=2000 group by 1,2,3
