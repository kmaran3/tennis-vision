select tour, source_file, source_row,
case when tourney_level in ('C','S','CC','J','E','35+H','50+H') or regexp_matches(coalesce(tourney_name,''),'(?i)125') then 'outside_main_tour'
when winner_id is null or loser_id is null or winner_id=loser_id then 'invalid_player_pair'
when try_strptime(tourney_date,'%Y%m%d') is null then 'invalid_date'
else 'duplicate_source_match_key' end as exclusion_reason
from {{ ref('stg_matches') }} s
where not exists(select 1 from {{ ref('matches') }} m where m.tour=s.tour and m.source_file=s.source_file and m.source_row=s.source_row)
