select match_id from {{ref('player_matches')}} group by 1 having count(*)<>2
