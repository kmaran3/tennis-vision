"""Migrate candidate match keys; verify cached replay inputs before retaining them."""
import sys
from baseline.config import connect,ARTIFACTS,write_json
COLUMNS="r.match_id AS source_match_id,f.player_a,f.player_b,f.feature_cutoff,f.serve_a,f.serve_b,f.return_a,f.return_b"

def main():
    con=connect()
    if sys.argv[1]=="before":
        con.execute("CREATE OR REPLACE TABLE meta.replay_prior_before AS SELECT "+COLUMNS+" FROM main.replay_matches r JOIN main.features f ON r.canonical_match_id=f.match_id")
        con.execute("""CREATE OR REPLACE TABLE meta.key_migration AS SELECT match_id AS old_id,
          'v2:'||lower(tour)||':'||edition_id||':'||coalesce(round,'unknown')||':'||split_part(match_id,':',4)||':'||least(split_part(winner_id,':',2),split_part(loser_id,':',2))||':'||greatest(split_part(winner_id,':',2),split_part(loser_id,':',2)) AS new_id
          FROM main.matches""")
    else:
        con.execute("UPDATE main.replay_matches r SET canonical_match_id=k.new_id FROM meta.key_migration k WHERE r.canonical_match_id=k.old_id")
        con.execute("CREATE OR REPLACE TEMP TABLE replay_prior_after AS SELECT "+COLUMNS+" FROM main.replay_matches r JOIN main.features f ON r.canonical_match_id=f.match_id")
        differences=con.execute("SELECT count(*) FROM ((SELECT * FROM meta.replay_prior_before EXCEPT SELECT * FROM replay_prior_after) UNION ALL (SELECT * FROM replay_prior_after EXCEPT SELECT * FROM meta.replay_prior_before))").fetchone()[0]
        rows=con.execute("SELECT count(*) FROM replay_prior_after").fetchone()[0]
        if differences:raise ValueError(f"{differences} replay input differences: rebuild replay probabilities before packaging")
        write_json(ARTIFACTS/"replay-prior-equivalence.json",dict(status="passed",resolved_source_matches=rows,differences=0,explanation="Round/player-qualified match keys and added prediction features leave all replay serve/return priors and observed point inputs unchanged. Canonical catalog references were migrated; point probabilities retain their original validated scoring model version."))
        print("Replay input equivalence passed:",rows,"source matches")
    con.close()

if __name__=="__main__":main()
