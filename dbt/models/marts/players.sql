with source_players as (
{% for tour in ['atp','wta'] %}
select '{{tour}}:'||player_id as player_id, '{{tour|upper}}' as tour,
trim(coalesce(name_first,'')||' '||coalesce(name_last,'')) as name, hand,
try_strptime(dob,'%Y%m%d')::date as birth_date, ioc as country, try_cast(height as int) as height,
source_file,source_row from {{source('raw',tour ~ '_players')}}
{% if not loop.last %} union all by name {% endif %}
{% endfor %}
), observed as (
select winner_id as player_id,tour,winner_name as name from {{ref('matches')}}
union all select loser_id,tour,loser_name from {{ref('matches')}}
), missing as (
select distinct player_id,tour,name from observed where player_id not in(select player_id from source_players)
qualify row_number() over(partition by player_id order by name)=1
)
select * from source_players
union all by name select * from missing
