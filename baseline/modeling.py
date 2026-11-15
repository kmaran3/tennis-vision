"""Expanding chronological model selection, one bounded training job at a time."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss, accuracy_score
from xgboost import XGBClassifier
from .config import ARTIFACTS, DATA, ROOT, connect, write_json, reserve,digest
from .temporal import FEATURES, elo_probability


def prepare(frame, features, means=None, scales=None):
    x=frame[features].to_numpy(dtype=float)
    missing=np.isnan(x)
    # Zero preserves the meaning of a missing difference. Missingness is explicit.
    x=np.nan_to_num(x,nan=0.0)
    if scales is None:
        scales=np.maximum(np.std(x,axis=0),1e-6)
    return np.column_stack((x/scales,missing.astype(float))),scales


def fit(frame, kind):
    features=["elo_diff"] if kind=="elo_logistic" else FEATURES
    x,scales=prepare(frame,features)
    flipped=frame.copy(); flipped[features]=-flipped[features]
    mx,_=prepare(flipped,features,scales=scales)
    y=frame.y.to_numpy()
    xx=np.vstack((x,mx)); yy=np.concatenate((y,1-y))
    if kind=="xgboost":
        model=XGBClassifier(n_estimators=80,max_depth=3,learning_rate=0.05,subsample=0.9,colsample_bytree=0.9,reg_lambda=5,n_jobs=1,random_state=17)
    else:
        model=LogisticRegression(C=0.2,max_iter=300,random_state=17)
    model.fit(xx,yy)
    return model,features,scales


def predict(model,frame,features,scales):
    x,_=prepare(frame,features,scales=scales)
    flip=frame.copy();flip[features]=-flip[features]
    mx,_=prepare(flip,features,scales=scales)
    return (model.predict_proba(x)[:,1]+1-model.predict_proba(mx)[:,1])/2


def scores(y,p):
    p=np.clip(p,1e-8,1-1e-8)
    bins=[]
    for lo in np.linspace(0,0.9,10):
        mask=(p>=lo)&(p<lo+0.1000001)
        if mask.any(): bins.append(dict(lower=round(float(lo),1),n=int(mask.sum()),predicted=float(p[mask].mean()),observed=float(y[mask].mean())))
    return dict(n=len(y),log_loss=float(log_loss(y,p,labels=[0,1])),brier=float(brier_score_loss(y,p)),accuracy=float(accuracy_score(y,p>=0.5)),calibration=bins)


def train():
    reserve(1)
    con=connect()
    df=con.execute("SELECT f.* FROM main.features f WHERE season>=2000 AND history_a>=10 AND history_b>=10 AND NOT EXISTS(SELECT 1 FROM main.odds_matches o WHERE o.match_id=f.match_id AND o.provider_observed_date<f.feature_cutoff)").df()
    snapshot=con.execute("SELECT snapshot FROM meta.build").fetchone()[0]
    import hashlib
    recipe_files=[ROOT/"baseline/modeling.py",ROOT/"baseline/temporal.py",ROOT/"baseline/identity.py",ROOT/"uv.lock",DATA/"identity-overrides.csv",*sorted((ROOT/"dbt/models").rglob("*.sql"))]
    recipe=hashlib.sha256("".join(digest(p) for p in recipe_files if p.exists()).encode()).hexdigest()[:10]
    all_predictions=[]; reports=[]; registry=[]
    model_dir=DATA/"models/prematch";model_dir.mkdir(parents=True,exist_ok=True)
    for tour in ("ATP","WTA"):
        subset=df[df.tour==tour].copy()
        for year in sorted(int(y) for y in subset.season.unique() if y>=2005):
            test_start=pd.Timestamp(year,1,1);val_start=pd.Timestamp(year-1,1,1)
            training=subset[(subset.feature_cutoff<val_start)&(subset.available_at<val_start)]
            validation=subset[(subset.feature_cutoff>=val_start)&(subset.available_at<test_start)]
            test=subset[subset.season==year]
            if len(training)<500 or len(validation)<100 or len(test)<50: continue
            y=validation.y.to_numpy(); options=[]
            for kind in ("elo_logistic","logistic","xgboost"):
                model,features,scales=fit(training,kind)
                p=predict(model,validation,features,scales)
                result=scores(y,p)
                options.append((kind,model,features,scales,result))
            # Retain simpler candidates within 0.002 validation log loss, and avoid
            # degrading Brier calibration by more than 0.002.
            best=min(o[4]["log_loss"] for o in options)
            best_brier=min(o[4]["brier"] for o in options)
            selected=next((o for o in options if o[4]["log_loss"]<=best+0.002 and o[4]["brier"]<=best_brier+0.002),min(options,key=lambda o:o[4]["log_loss"]))
            kind,model,features,scales,validation_score=selected
            version=f"{tour.lower()}-{year}-{snapshot[:10]}-{recipe}"
            model_file=model_dir/(version+".json")
            definition=dict(version=version,kind=kind,features=features,scales=scales.tolist(),trained_before=str(val_start.date()),valid_from=str(test_start.date()),valid_until=f"{year}-12-31",tour=tour,snapshot=snapshot,recipe=recipe)
            if kind=="xgboost":
                model.save_model(model_file.with_suffix(".xgb.json"));definition["xgboost_file"]=model_file.with_suffix(".xgb.json").name
            else:
                definition.update(coef=model.coef_[0].tolist(),intercept=float(model.intercept_[0]))
            write_json(model_file,definition);registry.append(definition)
            p=predict(model,test,features,scales)
            baseline=np.array([elo_probability(a,b) for a,b in zip(test.elo_a,test.elo_b)])
            rank=np.where(test.rank_diff.to_numpy()<0,0.65,np.where(test.rank_diff.to_numpy()>0,0.35,0.5))
            report=dict(tour=tour,season=year,version=version,training_matches=len(training),validation_matches=len(validation),selected=kind,validation={o[0]:o[4] for o in options},test=scores(test.y.to_numpy(),p),elo=scores(test.y.to_numpy(),baseline),higher_rank=scores(test.y.to_numpy(),rank),slices=[])
            for dimension in ("surface","level"):
                for value in test[dimension].dropna().unique():
                    mask=(test[dimension]==value).to_numpy()
                    report["slices"].append(dict(dimension=dimension,value=str(value),**scores(test.y.to_numpy()[mask],p[mask])))
            # Grouped tournament bootstrap on original match rows, never mirrored rows.
            rng=np.random.default_rng(17); groups=test.edition_id.to_numpy();ids=np.unique(groups)
            losses=-(test.y.to_numpy()*np.log(np.clip(p,1e-8,1))+(1-test.y.to_numpy())*np.log(np.clip(1-p,1e-8,1)))
            group_stats={g:(losses[groups==g].sum(),int((groups==g).sum())) for g in ids}
            samples=[]
            for _ in range(100):
                chosen=rng.choice(ids,len(ids),replace=True);samples.append(sum(group_stats[g][0] for g in chosen)/sum(group_stats[g][1] for g in chosen))
            report["tournament_bootstrap_log_loss_95pct"]=np.quantile(samples,[0.025,0.975]).tolist()
            reports.append(report)
            for r,prob,elo,rankp in zip(test.to_dict("records"),p,baseline,rank):
                all_predictions.append(dict(match_id=r["match_id"],tour=tour,season=year,surface=r["surface"],level=r["level"],player_a=r["player_a"],player_b=r["player_b"],y=r["y"],probability=float(prob),elo_probability=float(elo),rank_probability=float(rankp),model_version=version,prediction_kind="out_of_sample",feature_cutoff=r["feature_cutoff"]))
            print(f"Trained {version}: {kind}, test log loss {report['test']['log_loss']:.4f}",flush=True)
    if all_predictions:
        con.register("prediction_frame",pd.DataFrame(all_predictions));con.execute("CREATE OR REPLACE TABLE main.predictions AS SELECT * FROM prediction_frame")
    else:
        con.execute("CREATE OR REPLACE TABLE main.predictions(match_id VARCHAR, tour VARCHAR, season INT, surface VARCHAR,level VARCHAR,player_a VARCHAR,player_b VARCHAR,y INT,probability DOUBLE,elo_probability DOUBLE,rank_probability DOUBLE,model_version VARCHAR,prediction_kind VARCHAR,feature_cutoff DATE)")
    con.close()
    write_json(ARTIFACTS/"model-registry.json",registry)
    write_json(ARTIFACTS/"model-evaluation.json",dict(snapshot=snapshot,windows=reports,limitations=["Tournament-level dates and inferred 28-day availability; no unconditional leak-free claim.","No odds, realized weather, score, duration, or current-match statistics enter model inputs.","Ranking baseline probabilities are fixed 0.65/0.35; accuracy reflects higher-ranked selection.","Uncalibrated candidate probabilities; calibration is measured, not claimed."]))
    return reports


def model_probability(definition, values, directory):
    frame=pd.DataFrame([values]);features=definition["features"];scales=np.array(definition["scales"])
    if definition["kind"]=="xgboost":
        model=XGBClassifier();model.load_model(Path(directory)/definition["xgboost_file"])
        return float(predict(model,frame,features,scales)[0])
    x,_=prepare(frame,features,scales=scales);flip=frame.copy();flip[features]=-flip[features];mx,_=prepare(flip,features,scales=scales)
    coef=np.array(definition["coef"]);intercept=definition["intercept"]
    sigmoid=lambda z:1/(1+np.exp(-np.clip(z,-40,40)))
    return float((sigmoid(x@coef+intercept)[0]+1-sigmoid(mx@coef+intercept)[0])/2)
