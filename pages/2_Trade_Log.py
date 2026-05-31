"""Trade Log — filterable table, edit/delete, screenshot view (BLOB)."""
import io

import streamlit as st

from db import all_trades, delete_trade, get_trade, init_schema, update_trade
from stats import to_df

st.set_page_config(page_title="Trade Log · Trade Tracker", page_icon="📋", layout="wide")


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

st.title("📋 Trade Log")

df = to_df(all_trades())
if df.empty:
    st.info("No trades yet — log one first.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
f_type = c1.multiselect("Type", sorted(df["entry_type"].dropna().unique()))
f_status = c2.multiselect("Status", sorted(df["status"].dropna().unique()))
f_asset = c3.multiselect("Asset", sorted(df["asset"].dropna().unique()))
f_sweep = c4.multiselect("Sweep", sorted(df["sweep_state"].dropna().unique()))

view = df.copy()
if f_type:
    view = view[view["entry_type"].isin(f_type)]
if f_status:
    view = view[view["status"].isin(f_status)]
if f_asset:
    view = view[view["asset"].isin(f_asset)]
if f_sweep:
    view = view[view["sweep_state"].isin(f_sweep)]

st.caption(f"{len(view)} of {len(df)} trades")

display_cols = [
    "id", "date", "entry_type", "status", "asset", "direction", "sweep_state",
    "entry_trigger", "cisd_confirmed", "bias_alignment", "planned_rr",
    "actual_r", "outcome", "confidence",
]
st.dataframe(
    view[[c for c in display_cols if c in view.columns]],
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("Inspect & edit")
tid = st.selectbox("Trade id", view["id"].tolist())
t = get_trade(int(tid))

if t:
    left, right = st.columns([2, 1])
    with left:
        # don't dump the blob bytes into json
        st.json({k: v for k, v in t.items() if v is not None and k != "screenshot_blob"})
    with right:
        blob = t.get("screenshot_blob")
        if blob:
            try:
                st.image(io.BytesIO(blob), caption="Chart", use_container_width=True)
            except Exception as e:
                st.caption(f"Screenshot couldn't render: {e}")
        else:
            st.caption("No screenshot.")

    with st.expander("Edit core fields"):
        with st.form("edit_trade"):
            c1, c2, c3 = st.columns(3)
            actual_r = c1.number_input("Actual R", value=float(t["actual_r"] or 0.0), format="%.2f")
            outcome = c2.selectbox(
                "Outcome", ["win", "loss", "be"],
                index=(["win", "loss", "be"].index(t["outcome"]) if t["outcome"] in ["win", "loss", "be"] else 0),
            )
            status = c3.selectbox(
                "Status", ["open", "closed"],
                index=(["open", "closed"].index(t["status"]) if t["status"] in ["open", "closed"] else 0),
            )
            notes = st.text_area("Notes", value=t["notes"] or "")
            if st.form_submit_button("Save edits", type="primary"):
                update_trade(int(tid), {
                    "actual_r": actual_r, "outcome": outcome,
                    "status": status, "notes": notes or None,
                })
                st.success("Saved.")
                st.rerun()

    with st.expander("⚠️ Delete this trade"):
        if st.button(f"Delete #{tid}", type="secondary"):
            delete_trade(int(tid))
            st.success(f"Deleted #{tid}.")
            st.rerun()
