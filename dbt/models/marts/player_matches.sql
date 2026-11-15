{% for side,other,won in [('w','l',1),('l','w',0)] %}
select match_id,tour,edition_id,event,surface,level,season,observed_date,available_at,date_precision,
{% if side=='w' %} winner_id as player_id,loser_id as opponent_id {% else %} loser_id as player_id,winner_id as opponent_id {% endif %},
{{won}} as won,
{{side}}_ace as aces, {{side}}_df as double_faults, {{side}}_svpt as service_points,
{{side}}_1stIn as first_in, {{side}}_1stWon as first_won, {{side}}_2ndWon as second_won,
{{side}}_bpSaved as bp_saved, {{side}}_bpFaced as bp_faced,
{{other}}_svpt as opp_service_points, {{other}}_1stWon as opp_first_won, {{other}}_2ndWon as opp_second_won,
{{other}}_bpSaved as opp_bp_saved, {{other}}_bpFaced as opp_bp_faced,
source_file,source_row
from {{ref('matches')}} where completed
{% if not loop.last %} union all {% endif %}
{% endfor %}
