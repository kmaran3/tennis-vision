"""Generate MetricFlow semantics from the same registry used by API and analyst."""
from pathlib import Path
import yaml
from .config import ROOT
from .metrics import METRICS

def generate():
    measures=[];metrics=[]
    for name,(num,den,description) in METRICS.items():
        valid=f"({num}) IS NOT NULL AND ({den}) IS NOT NULL AND ({num})>=0 AND ({den})>=0"
        if name!="average_rally_length":valid+=f" AND ({num})<=({den})"
        for suffix,expr in (("numerator",num),("denominator",den)):
            measure=name+"_"+suffix
            measures.append(dict(name=measure,agg="sum",expr=f"CASE WHEN {valid} THEN ({expr}) END"))
            metrics.append(dict(name=measure,label=measure,type="simple",type_params={"measure":measure}))
        metrics.append(dict(name=name,label=description,type="ratio",type_params=dict(numerator=name+"_numerator",denominator=name+"_denominator")))
    semantic=dict(name="player_matches",model="ref('player_matches')",defaults={"agg_time_dimension":"observed_date"},entities=[dict(name="player_match",type="primary",expr="match_id || ':' || player_id"),dict(name="player",type="foreign",expr="player_id")],dimensions=[dict(name="observed_date",type="time",type_params={"time_granularity":"day"})]+[dict(name=n,type="categorical") for n in ("tour","surface","season","level")],measures=measures)
    (ROOT/"dbt/models/semantic.yml").write_text(yaml.safe_dump(dict(semantic_models=[semantic],metrics=metrics),sort_keys=False))
