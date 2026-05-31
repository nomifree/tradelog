"""Log page — two-step entry: open a trade, close it later."""
from datetime import date

import streamlit as st

from db import (get_trade, init_schema, insert_trade, open_trades,
                read_upload_bytes, update_trade)

st.set_page_config(page_title="Log · Trade Tracker", page_icon="📝", layout="wide")


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

st.title("📝 Log")

DIRECTION = ["long", "short"]
SESSION = ["asia", "london", "ny"]
HTF_BIAS = ["long", "short", "neutral"]
SWEEP = ["sweep", "no_sweep"]
TRIGGER = ["cisd_market", "fvg_fill"]
CISD = ["yes", "partial", "no"]
ALIGN = ["aligned", "counter", "none"]
OUTCOME = ["win", "loss", "be"]
TF = ["1m", "5m", "15m", "1h", "4h", "1d"]


def planned_rr(entry, sl, tp):
    try:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        return round(reward / risk, 2) if risk else None
    except (TypeError, ZeroDivisionError):
        return None


tab_open, tab_close = st.tabs(["➕ New Entry", "✅ Close Entry"])

# ── New entry ─────────────────────────────────────────────────────────────────
with tab_open:
    with st.form("new_entry", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        entry_type = c1.radio("Type", ["live", "observation"], horizontal=True)
        d = c2.date_input("Date", value=date.today())
        asset = c3.text_input("Asset", placeholder="BTCUSDT").upper().strip()

        c1, c2, c3 = st.columns(3)
        direction = c1.selectbox("Direction", DIRECTION)
        timeframe = c2.selectbox("Entry timeframe", TF, index=3)
        session = c3.selectbox("Session", SESSION)

        st.markdown("**Tags — the buckets the stats split on**")
        c1, c2, c3, c4 = st.columns(4)
        sweep_state = c1.selectbox("Sweep?", SWEEP)
        entry_trigger = c2.selectbox("Trigger", TRIGGER)
        cisd_confirmed = c3.selectbox("CISD", CISD)
        bias_alignment = c4.selectbox("Bias align", ALIGN)
        htf_bias = st.selectbox("HTF bias", HTF_BIAS)

        st.markdown("**Risk plan**")
        c1, c2, c3, c4 = st.columns(4)
        entry_price = c1.number_input("Entry", min_value=0.0, format="%.6f")
        planned_sl = c2.number_input("Planned SL", min_value=0.0, format="%.6f")
        planned_tp = c3.number_input("Planned TP", min_value=0.0, format="%.6f")
        size = c4.number_input("Size (opt)", min_value=0.0, format="%.4f")

        rr = planned_rr(entry_price, planned_sl, planned_tp)
        st.caption(f"Planned R:R = **{rr if rr is not None else '—'}**")

        confidence = st.slider("Confidence", 1, 5, 3)
        shot = st.file_uploader("Chart screenshot", type=["png", "jpg", "jpeg"])
        notes = st.text_area("Notes")

        obs_r = obs_outcome = None
        if entry_type == "observation":
            st.markdown("**Observation outcome** (what price would have done)")
            oc1, oc2 = st.columns(2)
            obs_r = oc1.number_input("Hypothetical R", value=0.0, format="%.2f")
            obs_outcome = oc2.selectbox("Outcome", OUTCOME, key="obs_oc")

        submitted = st.form_submit_button("Save entry", type="primary")
        if submitted:
            if not asset:
                st.error("Asset is required.")
            else:
                row = {
                    "entry_type": entry_type,
                    "status": "closed" if entry_type == "observation" else "open",
                    "date": str(d), "asset": asset, "direction": direction,
                    "timeframe": timeframe, "session": session, "htf_bias": htf_bias,
                    "sweep_state": sweep_state, "entry_trigger": entry_trigger,
                    "cisd_confirmed": cisd_confirmed, "bias_alignment": bias_alignment,
                    "entry_price": entry_price or None, "planned_sl": planned_sl or None,
                    "planned_tp": planned_tp or None, "planned_rr": rr,
                    "size": size or None, "confidence": confidence,
                    "screenshot_blob": read_upload_bytes(shot),
                    "notes": notes or None,
                }
                if entry_type == "observation":
                    row["actual_r"] = obs_r
                    row["outcome"] = obs_outcome
                tid = insert_trade(row)
                st.success(f"Saved #{tid} ({entry_type}).")

# ── Close entry ───────────────────────────────────────────────────────────────
with tab_close:
    opens = open_trades()
    if not opens:
        st.info("No open trades to close.")
    else:
        labels = {
            f"#{r['id']} · {r['date']} · {r['asset']} · {r['direction']} · {r['sweep_state']}": r["id"]
            for r in opens
        }
        pick = st.selectbox("Open trade", list(labels.keys()))
        tid = labels[pick]
        t = get_trade(tid)

        with st.form("close_entry"):
            c1, c2 = st.columns(2)
            exit_price = c1.number_input("Exit price", min_value=0.0, format="%.6f")
            holding_minutes = c2.number_input("Holding (min)", min_value=0, step=1)

            c1, c2 = st.columns(2)
            actual_r = c1.number_input("Actual R", value=0.0, format="%.2f")
            outcome = c2.selectbox("Outcome", OUTCOME)

            c1, c2 = st.columns(2)
            emotion = c1.text_input("Emotion", placeholder="calm / fomo / revenge")
            followed = c2.radio("Followed rules?", ["yes", "no"], horizontal=True)
            close_notes = st.text_area("Closing notes", value=t["notes"] or "")

            done = st.form_submit_button("Close trade", type="primary")
            if done:
                update_trade(tid, {
                    "status": "closed",
                    "exit_price": exit_price or None,
                    "holding_minutes": int(holding_minutes) or None,
                    "actual_r": actual_r,
                    "outcome": outcome,
                    "emotion": emotion or None,
                    "followed_rules": 1 if followed == "yes" else 0,
                    "notes": close_notes or None,
                })
                st.success(f"Closed #{tid}.")
                st.rerun()
