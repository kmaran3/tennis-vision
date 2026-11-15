"""Consumer feature fact: one player side per canonical match and cutoff."""
from .config import connect
from .temporal import FEATURES

def build():
    con=connect()
    queries=[]
    for side,other,sign in (("a","b",1),("b","a",-1)):
        columns=["match_id","edition_id","tour","surface","season","level","best_of",f"player_{side} AS player_id",f"player_{other} AS opponent_id",f"'{side.upper()}' AS side","feature_cutoff","available_at","max_contributing_time","date_precision","availability_inferred",f"elo_{side} AS elo",f"surface_elo_{side} AS surface_elo",f"serve_{side} AS serve_form",f"return_{side} AS return_form",f"history_{side} AS history_matches"]
        columns += [f"{sign}*{f} AS {f}" for f in FEATURES]
        queries.append("SELECT "+",".join(columns)+" FROM main.features")
    con.execute("CREATE OR REPLACE TABLE main.player_features AS "+" UNION ALL ".join(queries))
    count=con.execute("SELECT count(*) FROM (SELECT match_id FROM main.player_features GROUP BY 1 HAVING count(*)<>2 OR count(distinct player_id)<>2)").fetchone()[0]
    con.close()
    if count:raise ValueError("Player-feature grain failed")
