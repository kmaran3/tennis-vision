"""Small serving-only inference path; training libraries load only for tree models."""
from functools import lru_cache
import math
from pathlib import Path


def elo_probability(a,b):
    return 1/(1+10**((b-a)/400))


@lru_cache(maxsize=2)
def tree_model(path):
    from xgboost import XGBClassifier
    model=XGBClassifier(n_jobs=1);model.load_model(path)
    model.set_params(n_jobs=1)
    return model


def model_probability(definition,values,directory):
    features=definition['features'];scales=definition['scales']
    raw=[float(values.get(name)) if values.get(name) is not None else float('nan') for name in features]
    missing=[math.isnan(v) for v in raw]
    scaled=[0.0 if absent else value/scale for value,scale,absent in zip(raw,scales,missing)]
    a=scaled+[float(v) for v in missing]
    b=[-v for v in scaled]+[float(v) for v in missing]
    if definition['kind']=='xgboost':
        import numpy as np
        model=tree_model(str((Path(directory)/definition['xgboost_file']).resolve()))
        p=model.predict_proba(np.array([a,b],dtype=float))[:,1]
        return float((p[0]+1-p[1])/2)
    def probability(row):
        z=definition['intercept']+sum(c*v for c,v in zip(definition['coef'],row))
        return 1/(1+math.exp(-max(-40,min(40,z))))
    return (probability(a)+1-probability(b))/2
