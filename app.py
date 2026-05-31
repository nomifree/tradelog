"""Crypto Trade Tracker — hosted on Streamlit Cloud, data in Turso.

Run locally:   streamlit run app.py
"""
import streamlit as st

from db import all_trades, init_schema
from stats import sweep_verdict, to_df, what_if_no_sweep

st.set_page_config(
    page_title="Trade Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Password gate (skipped locally when no secret set) ───────────────────────
def require_password():
    try:
        pwd = st.secrets["password"]
    except (KeyError, FileNotFoundError):
        return  # no secret -> open access (local dev)
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

st.markdown("""
<style>
  .block-container { padding: 1.2rem 1rem; max-width: 1000px; }
  .verdict-card {
    background: #1e2130; border-radius: 12px; padding: 16px 18px;
    border-left: 5px solid #555; margin-bottom: 8px;
  }
  .v-win  { border-left-color: #00cc88; }
  .v-lose { border-left-color: #555; }
  h1 { font-size: 1.6rem !important; }
  h2 { font-size: 1.2rem !important; }
</style>
""", unsafe_allow_html=True)

init_schema()

st.title("📈 Crypto Trade Tracker")
st.caption("Does the liquidity sweep earn its keep? Log trades + observations, let the data decide.")

rows = all_trades()
df = to_df(rows)

if df.empty:
    st.info(
        "No trades yet. Open the **Log** page in the sidebar to record your first "
        "trade or observation."
    )
    st.stop()

n_live = int((df["entry_type"] == "live").sum())
n_obs = int((df["entry_type"] == "observation").sum())
n_open = int((df["status"] == "open").sum())

c1, c2, c3 = st.columns(3)
c1.metric("Live trades", n_live)
c2.metric("Observations", n_obs)
c3.metric("Open (need closing)", n_open)

st.divider()

st.subheader("Sweep vs No-Sweep — live trades")
v = sweep_verdict(df)


def verdict_card(title, b, is_winner):
    cls = "v-win" if is_winner else "v-lose"
    badge = " 🏆" if is_winner else ""
    wr = f"{b['win_rate']}%" if b["win_rate"] is not None else "—"
    exp = f"{b['expectancy']:+.2f}R" if b["expectancy"] is not None else "—"
    avg = f"{b['avg_r']:+.2f}R" if b["avg_r"] is not None else "—"
    warn = " ⚠️ needs more data" if b["low_confidence"] and b["n"] > 0 else ""
    st.markdown(
        f"""<div class="verdict-card {cls}">
        <div style="color:#aaa;font-size:0.9rem">{title}{badge}</div>
        <div style="font-size:1.8rem;font-weight:700">{exp}<span style="font-size:0.8rem;color:#888"> expectancy</span></div>
        <div style="color:#ccc">Win rate {wr} · Avg {avg} · n={b['n']}{warn}</div>
        </div>""",
        unsafe_allow_html=True,
    )


col_s, col_n = st.columns(2)
with col_s:
    verdict_card("WITH sweep", v["sweep"], v["winner"] == "sweep")
with col_n:
    verdict_card("WITHOUT sweep", v["no_sweep"], v["winner"] == "no_sweep")

if v["winner"] == "tie":
    st.info("Dead heat — sweep and no-sweep expectancy are equal so far.")
elif v["winner"] == "sweep":
    st.success("The sweep filter is adding edge — sweep entries carry higher expectancy.")
elif v["winner"] == "no_sweep":
    st.warning("No-sweep entries are outperforming — your sweep filter may be costing you. See the what-if on the Intelligence page.")
else:
    st.info("Not enough closed live trades on both sides yet to call it.")

wi = what_if_no_sweep(df)
if wi["n"] > 0:
    st.caption(
        f"What-if: taking every no-sweep observation ({wi['n']}) would have netted "
        f"**{wi['net_r']:+.2f}R**. Full breakdown on the Intelligence page."
    )

st.divider()
st.caption("Use the sidebar → **Log**, **Trade Log**, **Intelligence**.")
