"""Intelligence — ranked stats. Headline first, then deeper cuts."""
import streamlit as st

from db import all_trades, init_schema
from stats import (bucket_table, discipline, equity_curve, loss_conditions,
                   sweep_verdict, to_df, what_if_no_sweep)

st.set_page_config(page_title="Intelligence · Trade Tracker", page_icon="🧠", layout="wide")


def require_password():
    try:
        pwd = st.secrets["password"]
    except (KeyError, FileNotFoundError):
        return
    if st.session_state.get("auth_ok"):
        return
    st.markdown("### 🔒 Locked")
    with st.form("auth"):
        v = st.text_input("Password", type="password")
        if st.form_submit_button("Enter", type="primary"):
            if v == pwd:
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("Wrong password")
    st.stop()


require_password()
init_schema()

st.title("🧠 Intelligence")

df = to_df(all_trades())
if df.empty or df["actual_r"].notna().sum() == 0:
    st.info("Need closed trades with an R outcome before the intelligence layer has anything to chew on.")
    st.stop()

# ── 1. Headline verdict ───────────────────────────────────────────────────────
st.subheader("1 · Sweep vs No-Sweep verdict")
v = sweep_verdict(df)


def show_block(title, b):
    if b["n"] == 0:
        st.metric(title, "—", "no data")
        return
    flag = " ⚠️" if b["low_confidence"] else ""
    st.metric(
        f"{title}{flag}",
        f"{b['expectancy']:+.2f}R",
        f"win {b['win_rate']}% · n={b['n']}",
    )


c1, c2 = st.columns(2)
with c1:
    show_block("WITH sweep", v["sweep"])
with c2:
    show_block("WITHOUT sweep", v["no_sweep"])

if v["winner"] == "sweep":
    st.success("Sweep entries carry higher expectancy — the filter is earning its keep.")
elif v["winner"] == "no_sweep":
    st.warning("No-sweep entries outperform — your sweep filter may be costing you edge.")
elif v["winner"] == "tie":
    st.info("Tie — equal expectancy both sides so far.")
else:
    st.info("Not enough closed live trades on both sides to call it yet.")

st.divider()

# ── 2. Expectancy by bucket ───────────────────────────────────────────────────
st.subheader("2 · Expectancy by bucket (ranked)")
bt = bucket_table(df)
if bt.empty:
    st.caption("No live trades to bucket yet.")
else:
    show = bt.copy()
    show["flag"] = show["needs_data"].map({True: "⚠️ needs data", False: "✓"})
    show = show.drop(columns=["needs_data"])
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption(f"Buckets with n < 20 flagged — don't over-trust them.")

st.divider()

# ── 3. When I'm wrong ─────────────────────────────────────────────────────────
st.subheader("3 · When I'm wrong")
dim = st.selectbox("Break losses down by", ["session", "asset", "bias_alignment", "confidence"])
lc = loss_conditions(df, dim)
if lc.empty:
    st.caption("No closed live trades yet.")
else:
    st.dataframe(lc, use_container_width=True, hide_index=True)

st.divider()

# ── 4. Plan vs reality ────────────────────────────────────────────────────────
st.subheader("4 · Plan vs reality")
live = df[(df["entry_type"] == "live") & df["actual_r"].notna()]
if not live.empty and live["planned_rr"].notna().any():
    st.scatter_chart(live, x="planned_rr", y="actual_r")
    st.caption("Planned R:R (x) vs Actual R achieved (y). Points below the diagonal = underdelivering vs plan.")

disc = discipline(df)
if disc:
    d1, d2 = st.columns(2)
    f = disc.get("followed", {})
    b = disc.get("broke", {})
    with d1:
        if f.get("n"):
            st.metric("Rules followed", f"{f['expectancy']:+.2f}R", f"win {f['win_rate']}% · n={f['n']}")
        else:
            st.metric("Rules followed", "—")
    with d2:
        if b.get("n"):
            st.metric("Rules broken", f"{b['expectancy']:+.2f}R", f"win {b['win_rate']}% · n={b['n']}")
        else:
            st.metric("Rules broken", "—")

st.divider()

# ── 5. What-if ────────────────────────────────────────────────────────────────
st.subheader("5 · What-if: the cost of the sweep filter")
wi = what_if_no_sweep(df)
if wi["n"] == 0:
    st.caption("Log some no-sweep observations to populate this.")
else:
    st.metric(
        "If you'd taken every no-sweep observation",
        f"{wi['net_r']:+.2f}R",
        f"across {wi['n']} skipped setups",
    )
    if wi["net_r"] > 0:
        st.warning(f"Those skipped no-sweep setups would have netted +{wi['net_r']:.2f}R. Your filter may be too strict.")
    else:
        st.success(f"Skipping them saved you {abs(wi['net_r']):.2f}R. The filter is protecting you.")

st.divider()

# ── 6. Equity curve ───────────────────────────────────────────────────────────
st.subheader("6 · Equity curve (R)")
ec = equity_curve(df)
if ec.empty:
    st.caption("No closed live trades yet.")
else:
    st.line_chart(ec.set_index("date")["cum_r"])
    st.caption(f"Cumulative R across {len(ec)} live trades · net {ec['cum_r'].iloc[-1]:+.2f}R")
