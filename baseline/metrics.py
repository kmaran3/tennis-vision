"""Single governed registry; ratio of sums with pairwise-valid denominators."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .config import records

# numerator and denominator must be both available on each contributing row.
METRICS = {
    "match_win_rate": ("won", "1", "Completed-match wins / completed matches"),
    "first_serve_in": ("first_in", "service_points", "First serves in / service points"),
    "first_serve_won": ("first_won", "first_in", "First serve points won / first serves in"),
    "second_serve_won": ("second_won", "service_points-first_in", "Second serve points won / second serve opportunities, including double faults"),
    "return_points_won": ("opp_service_points-opp_first_won-opp_second_won", "opp_service_points", "Return points won / return points played"),
    "break_point_save": ("bp_saved", "bp_faced", "Break points saved / break points faced"),
    "break_point_conversion": ("opp_bp_faced-opp_bp_saved", "opp_bp_faced", "Break points converted / opponent break points faced"),
    "aces_per_service_point": ("aces", "service_points", "Aces / service points"),
    "double_faults_per_service_point": ("double_faults", "service_points", "Double faults / service points"),
}
METRICS.update({
    "average_rally_length": ("rally_shots","rally_points","Charted rally shots including serve, excluding terminal errors / parsed charted points"),
    "serve_wide_share": ("serve_wide","charted_serves","Wide final serve attempts per point / final attempts with known direction; second serve when played"),
    "serve_body_share": ("serve_body","charted_serves","Body final serve attempts per point / final attempts with known direction; second serve when played"),
    "serve_t_share": ("serve_t","charted_serves","T final serve attempts per point / final attempts with known direction; second serve when played"),
    "charted_match_coverage": ("charted_match","1","Matches with a verified charting bridge / completed matches"),
    "odds_match_coverage": ("odds_match","1","Matches with uniquely matched Valuebetennis records / completed matches"),
    "venue_coverage": ("venue_verified","1","Matches with a verified venue assignment / completed matches"),
    "weather_coverage": ("weather_available","1","Matches with cached verified-venue event-period weather / completed matches"),
})
ASOF_METRICS = {"elo":"Overall Elo at the last inferred result-availability time strictly before the cutoff", "surface_elo":"Surface Elo at the last inferred result-availability time strictly before the cutoff"}
DIMENSIONS = {"player_id", "tour", "surface", "season", "level"}

class MetricQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metrics: list[str] = Field(default_factory=lambda: ["match_win_rate"], min_length=1, max_length=20)
    group_by: list[str] = Field(default_factory=lambda: ["player_id"], max_length=5)
    tour: Literal["ATP", "WTA"] = "ATP"
    player_ids: list[str] = Field(default_factory=list, max_length=20)
    surface: Literal["Hard", "Clay", "Grass", "Carpet"] | None = None
    start: date | None = None
    end: date | None = None
    available_before: date | None = None
    limit: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def allowed(self):
        if any(x not in METRICS and x not in ASOF_METRICS for x in self.metrics) or any(x not in DIMENSIONS for x in self.group_by):
            raise ValueError("Unsupported metric or dimension")
        if any(x in ASOF_METRICS for x in self.metrics):
            if any(x not in ASOF_METRICS for x in self.metrics):raise ValueError("Query as-of ratings separately from rate aggregates")
            if self.available_before:raise ValueError("As-of ratings use end date rather than available_before")
            if self.start:raise ValueError("As-of ratings use end date only, not a period start")
            if "surface_elo" in self.metrics and not self.surface:raise ValueError("Choose a surface for surface Elo")
            if any(x not in ("player_id","tour","surface") for x in self.group_by):raise ValueError("As-of ratings cannot be aggregated across seasons or levels")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must precede end")
        if any(not p.startswith(self.tour.lower()+":") for p in self.player_ids):
            raise ValueError("Player IDs must belong to the requested tour")
        return self


def query_metrics(con, q: MetricQuery):
    cutoff = con.execute("SELECT max(observed_date) FROM main.matches WHERE tour=? AND observed_date>=DATE '2000-01-01'", [q.tour]).fetchone()[0]
    if cutoff is None:
        return {"rows": [], "filters": q.model_dump(mode="json"), "cutoff": None}
    end = q.end or q.available_before or cutoff
    start = q.start or max(date(2000, 1, 1), end-timedelta(weeks=52))
    if start < date(2000, 1, 1) or end > cutoff or start > end:
        raise ValueError(f"Supported statistics: 2000-01-01 through {cutoff}")
    if any(name in ASOF_METRICS for name in q.metrics):
        filters=["upper(split_part(player_id,':',1))=?","surface=?","available_at<?"]
        params=[q.tour,q.surface or "Hard",end]
        if q.player_ids:
            filters.append("player_id IN ("+",".join("?" for _ in q.player_ids)+")");params.extend(q.player_ids)
        sql="SELECT player_id,upper(split_part(player_id,':',1)) AS tour,surface,available_at,"+",".join(q.metrics)+" FROM main.rating_history WHERE "+" AND ".join(filters)+" QUALIFY row_number() OVER(PARTITION BY player_id ORDER BY available_at DESC)=1 ORDER BY player_id LIMIT ?"
        params.append(q.limit);rows=records(con,sql,params)
        return dict(rows=rows,filters={**q.model_dump(mode="json"),"start":None,"end":str(end)},cutoff=str(cutoff),aggregation="as_of_observation",warnings=["As-of rating, not an average or sum. Results use inferred tournament-date availability with a 28-day lag."])
    cols = list(dict.fromkeys(q.group_by)) + ["count(*) AS sample_matches"]
    for name in q.metrics:
        num, den, _ = METRICS[name]
        valid = f"({num}) IS NOT NULL AND ({den}) IS NOT NULL AND ({num})>=0 AND ({den})>=0"
        if name!="average_rally_length":valid+=f" AND ({num})<=({den})"
        cols += [f"sum(CASE WHEN {valid} THEN ({num}) END)::DOUBLE/nullif(sum(CASE WHEN {valid} THEN ({den}) END),0) AS {name}",
                 f"count(*) FILTER (WHERE {valid}) AS {name}_coverage_matches",
                 f"sum(CASE WHEN {valid} THEN ({den}) END) AS {name}_denominator"]
    filters = ["tour=?", "observed_date BETWEEN ? AND ?"]
    params = [q.tour, start, end]
    if q.available_before:
        if q.available_before>cutoff:raise ValueError("Unsupported availability cutoff beyond the verified source cutoff")
        filters.append("available_at<?");params.append(q.available_before)
    if q.surface:
        filters.append("surface=?"); params.append(q.surface)
    if q.player_ids:
        filters.append("player_id IN ("+",".join("?" for _ in q.player_ids)+")"); params.extend(q.player_ids)
    sql = "SELECT "+", ".join(cols)+" FROM main.player_matches WHERE "+" AND ".join(filters)
    if q.group_by:
        sql += " GROUP BY "+", ".join(dict.fromkeys(q.group_by))+" ORDER BY sample_matches DESC, "+", ".join(dict.fromkeys(q.group_by))
    sql += " LIMIT ?"; params.append(q.limit)
    return dict(rows=records(con, sql, params), filters={**q.model_dump(mode="json"), "start":str(start), "end":str(end)}, cutoff=str(cutoff), warnings=["Tournament dates are approximate; latest season is incomplete."])
