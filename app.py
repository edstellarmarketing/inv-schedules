"""Bulk Schedule Generator – Streamlit app."""

from datetime import date, datetime, time
import pandas as pd
import requests
import streamlit as st

from data import (
    COURSES, COUNTRIES, COURSE_PRICING, PRICING_TIERS,
    TRAINING_MODES, STATUSES, DAYS_OF_WEEK,
)
from generator import generate_schedules, rows_to_excel_bytes


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Bulk Generate Schedules", layout="wide")

st.markdown(
    """
    <style>
    .section-header { font-weight: 600; font-size: 0.9rem; color: #555; margin-bottom: 4px; }
    div[data-testid="stCheckbox"] label { font-size: 0.9rem; }
    .stAlert { font-size: 0.9rem; }
    .rate-source { font-size: 0.82rem; color: #666; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("**Schedules > Bulk Generate Schedules**")
st.title("Bulk Generate Schedules")
st.markdown("---")


# ── Session state defaults ────────────────────────────────────────────────────

# base_rates: {currency: rate_vs_usd | None}  — updated by fetch / adjust / reset
if "base_rates" not in st.session_state:
    st.session_state.base_rates = {c["currency"]: c["exchange_rate"] for c in COUNTRIES}

# version bumped whenever base_rates change so the data_editor resets
if "rates_version" not in st.session_state:
    st.session_state.rates_version = 0

if "rates_source" not in st.session_state:
    st.session_state.rates_source = "Default"

if "rates_fetched_at" not in st.session_state:
    st.session_state.rates_fetched_at = None

_DEFAULT_COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia",
    "Germany", "Netherlands", "Brazil", "New Zealand",
    "United Arab Emirates", "Singapore", "Saudi Arabia",
    "Qatar", "Malaysia", "Japan", "Sri Lanka", "Bangladesh",
    "South Africa", "Kenya", "Nigeria", "India",
]
if "country_select" not in st.session_state:
    st.session_state["country_select"] = _DEFAULT_COUNTRIES


# ── Helpers ───────────────────────────────────────────────────────────────────

def checkbox_row(label, keys, options, defaults):
    st.markdown(f'<p class="section-header">{label}</p>', unsafe_allow_html=True)
    cols = st.columns(len(options))
    selected = []
    for col, key, opt, default in zip(cols, keys, options, defaults):
        with col:
            if st.checkbox(opt, value=default, key=key):
                selected.append(opt)
    return selected


def week_checkbox_row(label, prefix, defaults):
    st.markdown(f'<p class="section-header">{label}</p>', unsafe_allow_html=True)
    cols = st.columns(5)
    selected = []
    for i, (col, wl, default) in enumerate(zip(cols, ["W1","W2","W3","W4","W5"], defaults), start=1):
        with col:
            if st.checkbox(wl, value=default, key=f"{prefix}_w{i}"):
                selected.append(i)
    return selected


def time_to_str(t: time) -> str:
    return t.strftime("%H:%M")


def _fetch_live_rates() -> dict:
    """Fetch USD-based exchange rates from open.er-api.com (no key required)."""
    resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
    resp.raise_for_status()
    return resp.json()["rates"]


def _bump_rates(new_rates: dict, source: str, fetched_at: str | None = None):
    """Update base_rates in session state and bump the version counter."""
    st.session_state.base_rates = new_rates
    st.session_state.rates_version += 1
    st.session_state.rates_source = source
    st.session_state.rates_fetched_at = fetched_at


# ── Lookup maps ───────────────────────────────────────────────────────────────

course_names    = [c["name"] for c in COURSES]
country_names   = [c["name"] for c in COUNTRIES]
tier_map        = {t["name"]: t for t in PRICING_TIERS}
country_map     = {c["name"]: c for c in COUNTRIES}
course_map      = {c["name"]: c for c in COURSES}
mode_labels     = [m["label"] for m in TRAINING_MODES]
mode_value_map  = {m["label"]: m["value"] for m in TRAINING_MODES}


# ── Course & Countries ────────────────────────────────────────────────────────

col_l, col_r = st.columns(2)
with col_l:
    selected_course_name = st.selectbox("Course *", course_names, index=0)
with col_r:
    selected_country_names = st.multiselect(
        "Countries *",
        country_names,
        key="country_select",
    )

# ── Bulk upload countries ─────────────────────────────────────────────────────

with st.expander("📎 Bulk Upload Countries"):
    up_l, up_r = st.columns([3, 1])

    with up_r:
        # Template download
        import io as _io
        _tmpl = "Country\n" + "\n".join(country_names)
        st.download_button(
            "⬇ Download Template",
            data=_tmpl.encode(),
            file_name="countries_template.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with up_l:
        uploaded = st.file_uploader(
            "Upload CSV or Excel — needs a **Country** column (or first column is used)",
            type=["csv", "xlsx", "xls"],
            label_visibility="visible",
        )

    if uploaded:
        try:
            if uploaded.name.endswith((".xlsx", ".xls")):
                _df_up = pd.read_excel(uploaded)
            else:
                _df_up = pd.read_csv(uploaded)

            # Find the country column (case-insensitive match, else first column)
            _col = next(
                (c for c in _df_up.columns if c.strip().lower() == "country"),
                _df_up.columns[0],
            )
            _raw = _df_up[_col].dropna().str.strip().tolist()

            _valid_set   = set(country_names)
            _recognised  = [n for n in _raw if n in _valid_set]
            _unrecognised = [n for n in _raw if n not in _valid_set]

            if _recognised:
                info_l, btn_add, btn_replace = st.columns([4, 1, 1])
                with info_l:
                    msg = f"✅ **{len(_recognised)}** recognised"
                    if _unrecognised:
                        msg += f"   ·   ⚠️ **{len(_unrecognised)}** unrecognised: " \
                               + ", ".join(_unrecognised[:5]) \
                               + ("…" if len(_unrecognised) > 5 else "")
                    st.markdown(msg)

                with btn_add:
                    if st.button("Add to selection", use_container_width=True):
                        merged = list(dict.fromkeys(
                            st.session_state["country_select"] + _recognised
                        ))
                        st.session_state["country_select"] = merged
                        st.rerun()

                with btn_replace:
                    if st.button("Replace selection", use_container_width=True):
                        st.session_state["country_select"] = _recognised
                        st.rerun()
            else:
                st.warning("No matching country names found in the file.")
                if _unrecognised:
                    st.caption("Unrecognised: " + ", ".join(_unrecognised[:10]))

        except Exception as exc:
            st.error(f"Could not parse file: {exc}")

# ── Dates ─────────────────────────────────────────────────────────────────────

col_l, col_r = st.columns(2)
with col_l:
    from_date = st.date_input("From Date *", value=date(2026, 5, 1))
with col_r:
    to_date = st.date_input("To Date *", value=date(2026, 8, 31))

# ── Pricing Tiers ─────────────────────────────────────────────────────────────

st.markdown('<p class="section-header">Pricing Tiers (based on selected course; leave unchecked for base price only)</p>', unsafe_allow_html=True)
tier_cols = st.columns(3)
with tier_cols[0]:
    use_bronze = st.checkbox("Bronze", value=True, key="tier_bronze")
with tier_cols[1]:
    use_silver = st.checkbox("Silver", value=True, key="tier_silver")
with tier_cols[2]:
    use_gold   = st.checkbox("Gold",   value=True, key="tier_gold")

# ── Training Days / Capacity ──────────────────────────────────────────────────

col_l, col_r = st.columns(2)
with col_l:
    training_days    = st.number_input("Training Days (same for weekday & weekend) *", min_value=1, max_value=30, value=3)
with col_r:
    default_capacity = st.number_input("Default Capacity *", min_value=1, max_value=500, value=20)

st.markdown("---")

# ── Weekday Schedule ──────────────────────────────────────────────────────────

st.markdown("### Weekday Schedule")
wd_batches = st.number_input(
    "No. of Weekday Batches per Month (0 to disable) *",
    min_value=0, max_value=5, value=2, key="wd_batches",
)

if wd_batches > 0:
    wd_day_format = checkbox_row(
        "Weekday Format (days of week)",
        [f"wd_day_{d}" for d in DAYS_OF_WEEK],
        DAYS_OF_WEEK,
        [d in ("Mon", "Tue", "Wed") for d in DAYS_OF_WEEK],
    )
    wd_weeks = week_checkbox_row("Weekday Weeks of Month", "wd", [True, False, True, False, False])
else:
    wd_day_format, wd_weeks = [], []

st.markdown("---")

# ── Weekend Schedule ──────────────────────────────────────────────────────────

st.markdown("### Weekend Schedule")
we_batches = st.number_input(
    "No. of Weekend Batches per Month (0 to disable) *",
    min_value=0, max_value=5, value=2, key="we_batches",
)

if we_batches > 0:
    we_day_format = checkbox_row(
        "Weekend Format (days of week)",
        [f"we_day_{d}" for d in DAYS_OF_WEEK],
        DAYS_OF_WEEK,
        [d in ("Fri", "Sat", "Sun") for d in DAYS_OF_WEEK],
    )
    we_weeks = week_checkbox_row("Weekend Weeks of Month", "we", [True, False, True, False, False])
else:
    we_day_format, we_weeks = [], []

st.markdown("---")

# ── Training Mode & Time Slots ────────────────────────────────────────────────

col_l, _ = st.columns(2)
with col_l:
    selected_mode_label = st.selectbox("Training Mode *", mode_labels, index=0)

st.markdown('<p class="section-header">Time Slots (enter in New York EST; stored in each country\'s local timezone) *</p>', unsafe_allow_html=True)
ts_l, ts_r = st.columns(2)
with ts_l:
    start_time_val = st.time_input("Start time *", value=time(9, 0),  key="start_time")
with ts_r:
    end_time_val   = st.time_input("End time *",   value=time(17, 0), key="end_time")

col_l, _ = st.columns(2)
with col_l:
    duration = st.number_input("Duration (hours) *", min_value=1, max_value=24, value=8)

col_l, _ = st.columns(2)
with col_l:
    selected_status = st.selectbox("Default Status *", STATUSES, index=0)

st.markdown("---")

# ── Exchange Rates ────────────────────────────────────────────────────────────

st.markdown("### Exchange Rates")

# Source badge + fetch controls
src_col, fetch_col, reset_col = st.columns([3, 1.2, 1.2])
with src_col:
    src_label = st.session_state.rates_source
    fetched_at = st.session_state.rates_fetched_at
    badge = f"**Source:** {src_label}"
    if fetched_at:
        badge += f"  ·  fetched at {fetched_at} UTC"
    st.markdown(badge)

with fetch_col:
    if st.button("🔄 Fetch Live Rates", use_container_width=True):
        with st.spinner("Fetching…"):
            try:
                live = _fetch_live_rates()
                new_rates = dict(st.session_state.base_rates)
                for c in COUNTRIES:
                    cur = c["currency"]
                    if cur in live:
                        new_rates[cur] = round(live[cur], 4)
                _bump_rates(new_rates, "Live", datetime.utcnow().strftime("%H:%M"))
                st.rerun()
            except Exception as exc:
                st.error(f"Fetch failed: {exc}")

with reset_col:
    if st.button("↺ Reset to Defaults", use_container_width=True):
        _bump_rates(
            {c["currency"]: c["exchange_rate"] for c in COUNTRIES},
            "Default",
        )
        st.rerun()

# Global ±% adjustment
st.markdown('<p class="section-header">Adjust all selected-country rates by a percentage</p>', unsafe_allow_html=True)
adj_l, adj_r, _ = st.columns([1.5, 1, 5])
with adj_l:
    adj_pct = st.number_input(
        "Adjustment (%)", value=0.0, step=0.5, format="%.2f",
        help="Positive = increase rates, negative = decrease. Applied to current rates on click.",
        label_visibility="collapsed",
        key="adj_pct",
    )
    st.caption("e.g.  +5  or  -3")
with adj_r:
    if st.button("Apply ±%", use_container_width=True):
        new_rates = {}
        for cur, rate in st.session_state.base_rates.items():
            if rate is not None:
                new_rates[cur] = round(rate * (1 + adj_pct / 100), 4)
            else:
                new_rates[cur] = None
        _bump_rates(new_rates, f"{st.session_state.rates_source} ({adj_pct:+.2f}%)")
        st.rerun()

# Build rate table for selected countries only
course_obj = course_map[selected_course_name]

def _bronze_preview(country_obj, rate):
    if rate is None:
        return None
    base = COURSE_PRICING.get((course_obj["id"], country_obj["region"]), 995)
    bronze_pct = PRICING_TIERS[0]["percentage"]
    return round(base * (1 + bronze_pct / 100) * rate, 2)

rate_rows = []
for name in selected_country_names:
    c = country_map[name]
    rate = st.session_state.base_rates.get(c["currency"], c["exchange_rate"])
    rate_rows.append({
        "Country":               name,
        "Currency":              c["currency"],
        "Exchange Rate (vs USD)": rate,
        "Bronze Price Preview":  _bronze_preview(c, rate),
    })

df_rates = pd.DataFrame(rate_rows) if rate_rows else pd.DataFrame(
    columns=["Country", "Currency", "Exchange Rate (vs USD)", "Bronze Price Preview"]
)

editor_key = f"rate_editor_v{st.session_state.rates_version}"

edited_rates_df = st.data_editor(
    df_rates,
    key=editor_key,
    column_config={
        "Country":  st.column_config.TextColumn("Country",  disabled=True),
        "Currency": st.column_config.TextColumn("Currency", disabled=True),
        "Exchange Rate (vs USD)": st.column_config.NumberColumn(
            "Exchange Rate (vs USD)",
            format="%.4f",
            min_value=0.0,
            help="Rate relative to 1 USD. Edit directly to override.",
        ),
        "Bronze Price Preview": st.column_config.NumberColumn(
            "Bronze Price Preview",
            format="%.2f",
            disabled=True,
            help="Base price × 1.15 × exchange rate (Bronze tier, for reference only).",
        ),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
)

# Recompute Bronze preview live from whatever rate the user typed
if not edited_rates_df.empty:
    def _live_bronze(row):
        c = country_map.get(row["Country"])
        if c is None:
            return None
        return _bronze_preview(c, row["Exchange Rate (vs USD)"])
    edited_rates_df["Bronze Price Preview"] = edited_rates_df.apply(_live_bronze, axis=1)

    # Persist inline edits back to base_rates so Apply ±% uses the latest values
    for _, row in edited_rates_df.iterrows():
        cur = row["Currency"]
        val = row["Exchange Rate (vs USD)"]
        st.session_state.base_rates[cur] = val if pd.notna(val) else None

st.markdown("---")

# ── Generate ──────────────────────────────────────────────────────────────────

col_btn, col_cancel = st.columns([1, 6])
with col_btn:
    generate_clicked = st.button("⬇ Generate & Download", type="primary", use_container_width=True)
with col_cancel:
    st.button("Cancel", use_container_width=False)

if generate_clicked:
    # ── Validation ────────────────────────────────────────────────────────────
    errors = []
    if not selected_country_names:
        errors.append("Select at least one country.")
    if from_date >= to_date:
        errors.append("From Date must be before To Date.")

    selected_tiers = []
    if use_bronze: selected_tiers.append(tier_map["Bronze"])
    if use_silver: selected_tiers.append(tier_map["Silver"])
    if use_gold:   selected_tiers.append(tier_map["Gold"])
    if not selected_tiers:
        errors.append("Select at least one pricing tier.")

    if wd_batches > 0 and not wd_day_format: errors.append("Select at least one weekday day.")
    if wd_batches > 0 and not wd_weeks:      errors.append("Select at least one weekday week.")
    if we_batches > 0 and not we_day_format: errors.append("Select at least one weekend day.")
    if we_batches > 0 and not we_weeks:      errors.append("Select at least one weekend week.")
    if wd_batches == 0 and we_batches == 0:
        errors.append("Enable at least one of weekday or weekend batches.")

    if errors:
        for e in errors: st.error(e)
        st.stop()

    # ── Build country list with rates from the edited table ───────────────────
    rate_lookup: dict[str, float | None] = {}
    if not edited_rates_df.empty:
        for _, row in edited_rates_df.iterrows():
            val = row["Exchange Rate (vs USD)"]
            rate_lookup[row["Country"]] = float(val) if pd.notna(val) else None

    countries_with_rates = []
    for name in selected_country_names:
        c = dict(country_map[name])
        c["exchange_rate"] = rate_lookup.get(name, c["exchange_rate"])
        countries_with_rates.append(c)

    # ── Build params ──────────────────────────────────────────────────────────
    params = {
        "course_id":               course_obj["id"],
        "course_name":             course_obj["name"],
        "from_date":               from_date,
        "to_date":                 to_date,
        "pricing_tiers":           selected_tiers,
        "training_days":           int(training_days),
        "default_capacity":        int(default_capacity),
        "weekday_batches_enabled": wd_batches > 0,
        "weekday_day_format":      wd_day_format,
        "weekday_weeks":           wd_weeks,
        "weekend_batches_enabled": we_batches > 0,
        "weekend_day_format":      we_day_format,
        "weekend_weeks":           we_weeks,
        "training_mode":           mode_value_map[selected_mode_label],
        "start_time":              time_to_str(start_time_val),
        "end_time":                time_to_str(end_time_val),
        "duration":                int(duration),
        "status":                  selected_status,
        "countries":               countries_with_rates,
    }

    # ── Generate & download ───────────────────────────────────────────────────
    with st.spinner("Generating schedules…"):
        rows = generate_schedules(params)

    if not rows:
        st.warning("No schedules generated. Check your date range and batch settings.")
        st.stop()

    xlsx_bytes = rows_to_excel_bytes(rows)
    filename = f"bulk-schedules-{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"

    st.success(
        f"Generated **{len(rows)}** schedule rows across "
        f"**{len(selected_country_names)}** countries."
    )

    st.download_button(
        label="⬇ Download Excel",
        data=xlsx_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    with st.expander("Preview (first 50 rows)", expanded=False):
        st.dataframe(pd.DataFrame(rows[:50]), use_container_width=True)
