"""Conservative MCP notation parser and source-qualified point/shot facts.

Notation reference: cached MatchChart 0.3.2.xlsm, Instructions tab. Unknown
symbols/penalty points remain excluded; no guessed stroke is emitted.
"""
from __future__ import annotations
import re
from datetime import datetime
import pandas as pd
from .config import connect,records,ARTIFACTS,write_json
from .identity import normalize,event_name

SHOT_TYPES={"f":"forehand","b":"backhand","r":"forehand_slice","s":"backhand_slice","v":"forehand_volley","z":"backhand_volley","o":"overhead","p":"backhand_overhead","u":"forehand_drop","y":"backhand_drop","l":"forehand_lob","m":"backhand_lob","h":"forehand_half_volley","i":"backhand_half_volley","j":"forehand_swing_volley","k":"backhand_swing_volley","t":"trick_shot","q":"unknown"}


def parse_sequence(sequence):
    text=str(sequence or "").strip()
    if not re.match(r"^[0456]",text):raise ValueError("unknown_or_penalty_serve")
    if re.search(r"[^0456123789fbrsvzopuylmhijktqnwdxg!+;=^*#@C\-]",text):raise ValueError("unsupported_notation_symbol")
    tokens=[dict(shot=1,type="serve",direction=text[0],token=text[0])]
    if re.fullmatch(r"[0456][+;=\-]*[nwdxefg!]",text):return tokens,0
    if "C" in text:raise ValueError("challenge_notation_requires_review")
    for m in re.finditer(r"[fbrsvzopuylmhijktq][0-9+;=^\-]*",text[1:]):
        token=m.group();directions=re.findall(r"[123]",token[1:])
        tokens.append(dict(shot=len(tokens)+1,type=SHOT_TYPES[token[0]],direction=directions[0] if directions else None,token=token))
    error=text.endswith(("@","#")) and len(tokens)>1
    rally_length=max(0,len(tokens)-int(error))
    return tokens,rally_length


def build_charting():
    con=connect()
    players=records(con,"SELECT player_id,tour,name FROM main.players")
    index={}
    for p in players:index.setdefault((p["tour"],normalize(p["name"])),set()).add(p["player_id"])
    canonical=records(con,"SELECT match_id,tour,winner_id,loser_id,event,observed_date,round FROM main.matches")
    pairs={}
    for m in canonical:pairs.setdefault((m["tour"],tuple(sorted((m["winner_id"],m["loser_id"])))),[]).append(m)
    bridge=[];unresolved=[]
    for tour in ("atp","wta"):
        for row in records(con,f"SELECT * FROM raw.chart_{tour}_matches"):
            try:day=datetime.strptime(row["Date"],"%Y%m%d").date()
            except (TypeError,ValueError):continue
            ids=[]
            for side in ("Player 1","Player 2"):
                candidates=index.get((tour.upper(),normalize(row[side])),set());ids.append(next(iter(candidates)) if len(candidates)==1 else None)
            candidates=[]
            if all(ids) and ids[0]!=ids[1]:
                candidates=[m for m in pairs.get((tour.upper(),tuple(sorted(ids))),[]) if -2<=(day-m["observed_date"]).days<=27 and event_name(m["event"])==event_name(row["Tournament"]) and (not row.get("Round") or m["round"]==row["Round"])]
            if len(candidates)==1:
                bridge.append(dict(source_match_id=row["match_id"],match_id=candidates[0]["match_id"],tour=tour.upper(),player1=ids[0],player2=ids[1],observed_date=day,resolution_method="unique_normalized_pair_event_round_date",source_file=row["source_file"],source_row=row["source_row"]))
            else:unresolved.append(dict(source_match_id=row["match_id"],tour=tour.upper(),reason="no_unique_main_tour_pair_event_round_date"))
    frame=pd.DataFrame(bridge)
    if frame.empty:raise ValueError("No main-tour charting bridges resolved")
    # Multiple chartings for a canonical match are alternatives, not extra matches.
    frame=frame.sort_values("source_match_id").drop_duplicates("match_id")
    con.register("chart_bridge_frame",frame);con.execute("CREATE OR REPLACE TABLE main.chart_matches AS SELECT * FROM chart_bridge_frame")
    allowed=set(frame.source_match_id)
    con.execute("CREATE OR REPLACE TABLE main.chart_points(source_match_id VARCHAR,point INT,server INT,winner INT,rally_length INT,serve_direction VARCHAR,source_file VARCHAR,source_row BIGINT)")
    con.execute("CREATE OR REPLACE TABLE main.shots(source_match_id VARCHAR,point INT,shot INT,type VARCHAR,direction VARCHAR,token VARCHAR,source_file VARCHAR,source_row BIGINT)")
    errors=[];point_batch=[];shot_batch=[]
    def flush():
        if point_batch:
            con.register("point_batch",pd.DataFrame(point_batch));con.execute("INSERT INTO main.chart_points BY NAME SELECT * FROM point_batch");point_batch.clear()
        if shot_batch:
            con.register("shot_batch",pd.DataFrame(shot_batch));con.execute("INSERT INTO main.shots BY NAME SELECT * FROM shot_batch");shot_batch.clear()
    for tour in ("atp","wta"):
        cursor=con.cursor();cursor.execute(f'SELECT match_id,Pt,Svr,PtWinner,"1st","2nd",source_file,source_row FROM raw.chart_{tour}_points ORDER BY match_id,try_cast(Pt AS INT),source_file,source_row')
        seen=set()
        while True:
            batch=cursor.fetchmany(5000)
            if not batch:break
            for mid,pt,server,winner,first,second,file,row_number in batch:
                if mid not in allowed:continue
                try:
                    point=int(pt);sv=int(server);win=int(winner)
                    if sv not in (1,2) or win not in (1,2):raise ValueError("unknown_point_outcome")
                    key=(mid,point)
                    if key in seen:raise ValueError("duplicate_point")
                    seen.add(key)
                    tokens,length=parse_sequence(second or first)
                    point_batch.append(dict(source_match_id=mid,point=point,server=sv,winner=win,rally_length=length,serve_direction=tokens[0]["direction"],source_file=file,source_row=row_number))
                    for token in tokens:shot_batch.append(dict(source_match_id=mid,point=point,**token,source_file=file,source_row=row_number))
                except (ValueError,TypeError) as error:errors.append(dict(source_match_id=mid,source_row=row_number,reason=str(error)))
            flush()
        cursor.close()
    # Statistics describe only fully parsed points; coverage remains visible.
    con.execute("""CREATE OR REPLACE TABLE main.chart_player_metrics AS
      SELECT m.match_id,m.player1 AS player_id,count(*) AS rally_points,sum(p.rally_length) AS rally_shots,
        count(*) FILTER(WHERE p.server=1 AND serve_direction='4') AS serve_wide,
        count(*) FILTER(WHERE p.server=1 AND serve_direction='5') AS serve_body,
        count(*) FILTER(WHERE p.server=1 AND serve_direction='6') AS serve_t,
        count(*) FILTER(WHERE p.server=1 AND serve_direction IN ('4','5','6')) AS charted_serves
      FROM main.chart_points p JOIN main.chart_matches m USING(source_match_id) GROUP BY 1,2
      UNION ALL SELECT m.match_id,m.player2,count(*),sum(p.rally_length),
        count(*) FILTER(WHERE p.server=2 AND serve_direction='4'),count(*) FILTER(WHERE p.server=2 AND serve_direction='5'),
        count(*) FILTER(WHERE p.server=2 AND serve_direction='6'),count(*) FILTER(WHERE p.server=2 AND serve_direction IN ('4','5','6'))
      FROM main.chart_points p JOIN main.chart_matches m USING(source_match_id) GROUP BY 1,2""")
    con.execute("""CREATE OR REPLACE TABLE main.chart_shot_profiles AS
      SELECT m.match_id,
      CASE WHEN (s.shot%2=1 AND p.server=1) OR(s.shot%2=0 AND p.server=2) THEN m.player1 ELSE m.player2 END AS player_id,
      s.type,count(*) AS shots
      FROM main.shots s JOIN main.chart_points p USING(source_match_id,point)
      JOIN main.chart_matches m USING(source_match_id) GROUP BY 1,2,3""")
    counts=records(con,"SELECT tour,count(*) AS charted_matches FROM main.chart_matches GROUP BY 1")
    report=dict(bridged_matches=len(frame),coverage=counts,parsed_points=con.execute("SELECT count(*) FROM main.chart_points").fetchone()[0],parsed_shots=con.execute("SELECT count(*) FROM main.shots").fetchone()[0],point_errors=errors,match_exclusions=unresolved,parser_version="mcp-v1",limitations=["Unsupported notation is excluded with provenance; coverage is not complete.","Rally length includes the serve and excludes the terminal error attempt.","Shot facts retain unknown stroke markers; ambiguous main-tour match joins are rejected."])
    write_json(ARTIFACTS/"charting-coverage.json",report);con.close();return report


def attach_metric_columns():
    con=connect()
    for name in ("rally_points","rally_shots","serve_wide","serve_body","serve_t","charted_serves"):
        con.execute(f"ALTER TABLE main.player_matches ADD COLUMN IF NOT EXISTS {name} BIGINT")
        con.execute(f"UPDATE main.player_matches p SET {name}=c.{name} FROM main.chart_player_metrics c WHERE p.match_id=c.match_id AND p.player_id=c.player_id")
    for name in ("charted_match","odds_match","venue_verified","weather_available"):
        con.execute(f"ALTER TABLE main.player_matches ADD COLUMN IF NOT EXISTS {name} INT DEFAULT 0")
    con.execute("UPDATE main.player_matches SET charted_match=1 WHERE match_id IN(SELECT match_id FROM main.chart_matches)")
    from .config import METRIC_VERSION
    con.execute("UPDATE meta.build SET metric_version=?",[METRIC_VERSION])
    con.execute("UPDATE main.player_matches SET odds_match=1 WHERE match_id IN(SELECT match_id FROM main.odds_matches)")
    con.execute("UPDATE main.player_matches p SET venue_verified=CASE WHEN v.venue_status='verified' THEN 1 ELSE 0 END,weather_available=CASE WHEN v.weather_status='cached_event_period' THEN 1 ELSE 0 END FROM main.venue_coverage v WHERE p.tour=v.tour AND p.edition_id=v.edition_id")
    con.close()
