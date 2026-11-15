select
  'v2:' || lower(tour) || ':' || tourney_id || ':' || coalesce(round,'unknown') || ':' || match_num || ':' || least(winner_id,loser_id) || ':' || greatest(winner_id,loser_id) as match_id,
  tour, tourney_id as edition_id, tourney_name as event, surface, tourney_level as level,
  try_strptime(tourney_date, '%Y%m%d')::date as observed_date,
  'tournament' as date_precision,
  try_strptime(tourney_date, '%Y%m%d')::date as feature_cutoff,
  try_strptime(tourney_date, '%Y%m%d')::date + interval 28 day as available_at,
  true as availability_inferred,
  extract(year from try_strptime(tourney_date, '%Y%m%d'))::int as season,
  lower(tour)||':'||winner_id as winner_id, winner_name,
  lower(tour)||':'||loser_id as loser_id, loser_name,
  try_cast(winner_rank as double) as winner_rank,
  try_cast(loser_rank as double) as loser_rank,
  {% for side in ['winner','loser'] %}
  {% for field in ['age','ht'] %}
  try_cast({{side}}_{{field}} as double) as {{side}}_{{field}},
  {% endfor %}
  {{side}}_hand,
  {% endfor %}
  score, round, try_cast(best_of as int) as best_of,
  not regexp_matches(coalesce(score,''), '(?i)(RET|W/O|DEF|ABN|UNF|WALK)') and coalesce(score,'')<>'' as completed,
  {% for pre in ['w','l'] %}
  {% for stat in ['ace','df','svpt','1stIn','1stWon','2ndWon','SvGms','bpSaved','bpFaced'] %}
  try_cast({{pre}}_{{stat}} as int) as {{pre}}_{{stat}},
  {% endfor %}
  {% endfor %}
  source_file, source_row
from {{ ref('stg_matches') }}
where ((tour='ATP' and tourney_level in ('G','M','A','F','D','O')) or (tour='WTA' and tourney_level in ('G','W','F','D','O','I','P','PM','T1','T2','T3','T4','T5')))
  and not(tour='WTA' and regexp_matches(coalesce(tourney_name,''),'(?i)(125|\\b10k\\b|\\b25k\\b)')) and winner_id is not null and loser_id is not null
  and winner_id<>loser_id and try_strptime(tourney_date, '%Y%m%d') is not null
qualify row_number() over (partition by tour, tourney_id, round, match_num, least(winner_id,loser_id), greatest(winner_id,loser_id) order by source_file,source_row)=1
