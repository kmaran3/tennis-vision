{% for tour in ['atp','wta'] %}
select '{{tour}}:'||player as player_id, '{{tour|upper}}' as tour,
try_strptime(ranking_date,'%Y%m%d')::date as ranking_date,
try_cast(rank as int) as rank,try_cast(points as double) as points,source_file,source_row
from {{source('raw',tour ~ '_rankings')}}
where try_strptime(ranking_date,'%Y%m%d') is not null and try_cast(rank as int)>0
qualify row_number() over(partition by player,ranking_date order by source_file,source_row)=1
{% if not loop.last %} union all {% endif %}
{% endfor %}
