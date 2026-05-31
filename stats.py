"""Trade tracker — intelligence layer. All stats are R-native."""
import pandas as pd

LOW_CONFIDENCE_N = 20  # buckets below this are flagged "needs more data"

TAG_COLS = ["sweep_state", "entry_trigger", "cisd_confirmed", "bias_alignment"]


def to_df(rows) -> pd.DataFrame:
    """sqlite3.Row list -> DataFrame with numeric coercion."""
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    for col in ["entry_price", "exit_price", "size", "planned_sl", "planned_tp",
                "planned_rr", "actual_r", "holding_minutes", "confidence",
                "followed_rules"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _block(df: pd.DataFrame) -> dict:
    """Summary stats for a slice of trades. Uses actual_r only."""
    r = df["actual_r"].dropna() if "actual_r" in df else pd.Series(dtype=float)
    n = int(len(r))
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_r": None, "expectancy": None,
                "avg_win_r": None, "avg_loss_r": None, "total_r": 0.0,
                "low_confidence": True}
    wins = r[r > 0]
    losses = r[r < 0]
    return {
        "n": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_r": round(r.mean(), 3),
        "expectancy": round(r.mean(), 3),  # mean R per trade
        "avg_win_r": round(wins.mean(), 3) if len(wins) else None,
        "avg_loss_r": round(losses.mean(), 3) if len(losses) else None,
        "total_r": round(r.sum(), 2),
        "low_confidence": n < LOW_CONFIDENCE_N,
    }


def sweep_verdict(df: pd.DataFrame) -> dict:
    """Headline: sweep vs no_sweep on LIVE trades. Returns both blocks + winner."""
    if df.empty:
        return {"sweep": _block(df), "no_sweep": _block(df), "winner": None}
    live = df[df["entry_type"] == "live"]
    sweep = _block(live[live["sweep_state"] == "sweep"])
    no_sweep = _block(live[live["sweep_state"] == "no_sweep"])
    winner = None
    if sweep["expectancy"] is not None and no_sweep["expectancy"] is not None:
        if sweep["expectancy"] > no_sweep["expectancy"]:
            winner = "sweep"
        elif no_sweep["expectancy"] > sweep["expectancy"]:
            winner = "no_sweep"
        else:
            winner = "tie"
    return {"sweep": sweep, "no_sweep": no_sweep, "winner": winner}


def bucket_table(df: pd.DataFrame, by=None) -> pd.DataFrame:
    """Expectancy ranked by tag combination (live trades)."""
    by = by or TAG_COLS
    if df.empty:
        return pd.DataFrame()
    live = df[df["entry_type"] == "live"].copy()
    if live.empty:
        return pd.DataFrame()
    out = []
    for keys, grp in live.groupby(by, dropna=False):
        b = _block(grp)
        if b["n"] == 0:
            continue
        row = dict(zip(by, keys if isinstance(keys, tuple) else (keys,)))
        row.update({
            "n": b["n"], "win_rate": b["win_rate"], "expectancy": b["expectancy"],
            "total_r": b["total_r"], "needs_data": b["low_confidence"],
        })
        out.append(row)
    res = pd.DataFrame(out)
    return res.sort_values("expectancy", ascending=False) if not res.empty else res


def loss_conditions(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Loss-rate breakdown by a dimension (session/asset/bias_alignment/confidence)."""
    if df.empty or dim not in df:
        return pd.DataFrame()
    live = df[(df["entry_type"] == "live") & df["actual_r"].notna()].copy()
    if live.empty:
        return pd.DataFrame()
    live["is_loss"] = live["actual_r"] < 0
    g = live.groupby(dim).agg(
        n=("actual_r", "size"),
        loss_rate=("is_loss", lambda s: round(s.mean() * 100, 1)),
        avg_r=("actual_r", lambda s: round(s.mean(), 3)),
    ).reset_index()
    return g.sort_values("loss_rate", ascending=False)


def discipline(df: pd.DataFrame) -> dict:
    """Win rate when rules followed vs broken."""
    if df.empty:
        return {}
    live = df[(df["entry_type"] == "live") & df["actual_r"].notna()].copy()
    res = {}
    for label, val in [("followed", 1), ("broke", 0)]:
        sub = live[live["followed_rules"] == val]
        res[label] = _block(sub)
    return res


def what_if_no_sweep(df: pd.DataFrame) -> dict:
    """Net R if every no_sweep OBSERVATION had been taken."""
    if df.empty:
        return {"n": 0, "net_r": 0.0}
    obs = df[(df["entry_type"] == "observation")
             & (df["sweep_state"] == "no_sweep")
             & df["actual_r"].notna()]
    return {"n": int(len(obs)), "net_r": round(obs["actual_r"].sum(), 2)}


def equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative R over time for live closed trades."""
    if df.empty:
        return pd.DataFrame()
    live = df[(df["entry_type"] == "live") & df["actual_r"].notna()].copy()
    if live.empty:
        return pd.DataFrame()
    live = live.sort_values(["date", "id"])
    live["cum_r"] = live["actual_r"].cumsum()
    return live[["date", "actual_r", "cum_r"]]
