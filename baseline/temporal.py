"""Conservative, tournament-frozen features. Outcomes become available after 28 days."""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import timedelta
import heapq
import math
import pandas as pd
from .config import connect, WAREHOUSE

FEATURES = ["elo_diff", "surface_elo_diff", "rank_diff", "serve_diff", "return_diff", "form_diff", "age_diff", "height_diff", "experience_diff", "format_diff", "hand_diff", "slam_elo_diff", "high_tier_elo_diff"]

def elo_probability(a, b):
    return 1/(1+10**((b-a)/400))

def build_features(path=WAREHOUSE):
    con = connect(path)
    matches = con.execute("""SELECT m.*, rw.rank AS rank_w_asof, rw.ranking_date AS rank_w_date, rl.rank AS rank_l_asof, rl.ranking_date AS rank_l_date
      FROM main.matches m
      ASOF LEFT JOIN main.rankings rw ON m.winner_id=rw.player_id AND m.observed_date>rw.ranking_date
      ASOF LEFT JOIN main.rankings rl ON m.loser_id=rl.player_id AND m.observed_date>rl.ranking_date
      WHERE m.completed ORDER BY m.observed_date,m.match_id""").df()
    ratings = defaultdict(lambda: 1500.0)
    surface_ratings = defaultdict(lambda: 1500.0)
    history = defaultdict(deque)
    experience = defaultdict(int)
    last = {}
    pending = []
    output = []
    rating_history=[]
    for row in matches.to_dict("records"):
        day = row["observed_date"].date()
        # Strict inequality: same-day availability is not assumed at midnight.
        while pending and pending[0][0] < day:
            release_day = pending[0][0]
            batch = []
            while pending and pending[0][0] == release_day:
                batch.append(heapq.heappop(pending)[2])
            delta = defaultdict(float); sdelta = defaultdict(float)
            for old in batch:
                w,l,s = old["winner_id"],old["loser_id"],old["surface"]
                d=24*(1-elo_probability(ratings[w],ratings[l]))
                sd=24*(1-elo_probability(surface_ratings[w,s],surface_ratings[l,s]))
                delta[w]+=d;delta[l]-=d;sdelta[w,s]+=sd;sdelta[l,s]-=sd
                for p,won,prefix in ((w,1,"w"),(l,0,"l")):
                    history[p].append((release_day,won,old,prefix));experience[p]+=1;last[p]=release_day
            # Matches sharing a proxy date update in a batch, never by match_num.
            for p,d in delta.items(): ratings[p]+=d
            for p,d in sdelta.items(): surface_ratings[p]+=d
            for p in delta:
                for surf in ("Hard","Clay","Grass","Carpet"):
                    rating_history.append(dict(player_id=p,surface=surf,available_at=release_day,elo=ratings[p],surface_elo=surface_ratings[p,surf]))
        w,l,s = row["winner_id"],row["loser_id"],row["surface"]
        a,b = sorted((w,l))
        stats = {}
        for p in (a,b):
            while history[p] and history[p][0][2]["observed_date"].date() < day-timedelta(weeks=52): history[p].popleft()
            sv=sp=rw=rp=wins=0
            for _,won,old,pre in history[p]:
                op="l" if pre=="w" else "w"
                values=[old.get(pre+"_svpt"),old.get(pre+"_1stWon"),old.get(pre+"_2ndWon")]
                if all(v is not None and not pd.isna(v) for v in values) and values[0]>0 and 0<=values[1]+values[2]<=values[0]:
                    sp+=values[0];sv+=values[1]+values[2]
                vals=[old.get(op+"_svpt"),old.get(op+"_1stWon"),old.get(op+"_2ndWon")]
                if all(v is not None and not pd.isna(v) for v in vals) and vals[0]>0 and 0<=vals[1]+vals[2]<=vals[0]:
                    rp+=vals[0];rw+=vals[0]-vals[1]-vals[2]
                wins+=won
            stats[p]=(sv/sp if sp else float("nan"),rw/rp if rp else float("nan"),wins/len(history[p]) if history[p] else float("nan"))
        pre_a="winner" if a==w else "loser";pre_b="winner" if b==w else "loser"
        def difference(field):
            x,y=row.get(pre_a+"_"+field),row.get(pre_b+"_"+field)
            if field=="rank":
                x=row["rank_w_asof"] if a==w else row["rank_l_asof"]
                y=row["rank_l_asof"] if a==w else row["rank_w_asof"]
            return float(x)-float(y) if x is not None and y is not None and not pd.isna(x) and not pd.isna(y) else float("nan")
        rank_dates=[row[k].date() for k in ("rank_w_date","rank_l_date") if row[k] is not None and not pd.isna(row[k])]
        max_time=max([last[p] for p in (a,b) if p in last]+rank_dates,default=None)
        output.append(dict(match_id=row["match_id"],edition_id=row.get("edition_id",str(row["match_id"]).rsplit(":",1)[0]), tour=row["tour"], surface=s, season=day.year, level=row["level"], best_of=row["best_of"],
                           player_a=a,player_b=b,y=int(a==w), feature_cutoff=day, available_at=day+timedelta(days=28),
                           max_contributing_time=max_time,date_precision="tournament", availability_inferred=True,
                           elo_a=ratings[a],elo_b=ratings[b],surface_elo_a=surface_ratings[a,s],surface_elo_b=surface_ratings[b,s],
                           history_a=experience[a],history_b=experience[b],serve_a=stats[a][0],serve_b=stats[b][0],return_a=stats[a][1],return_b=stats[b][1],
                           elo_diff=ratings[a]-ratings[b], surface_elo_diff=surface_ratings[a,s]-surface_ratings[b,s],
                           hand_diff=(int(row.get(pre_a+"_hand")=="L")-int(row.get(pre_b+"_hand")=="L")) if row.get(pre_a+"_hand") in ("L","R") and row.get(pre_b+"_hand") in ("L","R") else float("nan"),
                           slam_elo_diff=(ratings[a]-ratings[b])/400*int(row["level"]=="G"),
                           high_tier_elo_diff=(ratings[a]-ratings[b])/400*int(row["level"] in ("M","PM","P","F","T1","T2")),
                           format_diff=(row["best_of"]-3)*(ratings[a]-ratings[b])/400, rank_diff=difference("rank"), serve_diff=stats[a][0]-stats[b][0],return_diff=stats[a][1]-stats[b][1],
                           form_diff=stats[a][2]-stats[b][2], age_diff=difference("age"),height_diff=difference("ht"),experience_diff=experience[a]-experience[b]))
        heapq.heappush(pending,(day+timedelta(days=28),row["match_id"],row))
    frame=pd.DataFrame(output)
    con.register("feature_frame",frame)
    con.execute("CREATE OR REPLACE TABLE main.features AS SELECT * FROM feature_frame")
    con.register("ratings_frame",pd.DataFrame(rating_history))
    con.execute("CREATE OR REPLACE TABLE main.rating_history AS SELECT * FROM ratings_frame")
    con.close()
    return len(frame)
