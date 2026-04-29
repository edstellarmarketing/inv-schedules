"""Bulk Schedule Generator – Streamlit app."""

from datetime import date, datetime
import pandas as pd
import requests
import streamlit as st

from data import (
    COURSES, COUNTRIES, COURSE_PRICING, PRICING_TIERS,
    TRAINING_MODES, STATUSES,
)
from generator import (
    generate_schedules_bulk, parse_bulk_csv,
    rows_to_excel_bytes, compute_tz_preview, to_12h,
)


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Bulk Generate Schedules", layout="wide")

st.markdown(
    """
    <style>
    .section-header { font-weight: 600; font-size: 0.9rem; color: #555; margin-bottom: 4px; }
    .stAlert { font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("**Schedules > Bulk Generate Schedules**")
st.title("Bulk Generate Schedules")
st.markdown("---")


# ── Session state ─────────────────────────────────────────────────────────────

if "base_rates" not in st.session_state:
    st.session_state.base_rates = {c["currency"]: c["exchange_rate"] for c in COUNTRIES}
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
if "bulk_country_select" not in st.session_state:
    st.session_state["bulk_country_select"] = _DEFAULT_COUNTRIES

if "bulk_configs" not in st.session_state:
    st.session_state.bulk_configs = []
if "bulk_warnings" not in st.session_state:
    st.session_state.bulk_warnings = []
if "bulk_course_map" not in st.session_state:
    st.session_state.bulk_course_map = {}
if "bulk_keep_times" not in st.session_state:
    st.session_state.bulk_keep_times = []

if "pending_generate" not in st.session_state:
    st.session_state.pending_generate = False
if "tz_confirmed" not in st.session_state:
    st.session_state.tz_confirmed = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_live_rates() -> dict:
    resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
    resp.raise_for_status()
    return resp.json()["rates"]


def _bump_rates(new_rates: dict, source: str, fetched_at: str | None = None):
    st.session_state.base_rates = new_rates
    st.session_state.rates_version += 1
    st.session_state.rates_source = source
    st.session_state.rates_fetched_at = fetched_at


# ── Timezone preview dialog ───────────────────────────────────────────────────

@st.dialog("🌍 Timezone Conversion Preview", width="large")
def _tz_preview_dialog(rows, input_start_12h, input_end_12h, ref_date_str, bulk_note):
    st.caption(
        f"Reference date: **{ref_date_str}** · Input times in **EST (America/New_York)**"
    )
    st.markdown(f"**Input:** {input_start_12h} – {input_end_12h} EST")
    if bulk_note:
        st.info(bulk_note)
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Country":          st.column_config.TextColumn("Country", width="medium"),
            "Timezone":         st.column_config.TextColumn("TZ", width="small"),
            "UTC Offset":       st.column_config.TextColumn("UTC Offset", width="small"),
            "Local Start Time": st.column_config.TextColumn("Local Start", width="small"),
            "Local End Time":   st.column_config.TextColumn("Local End", width="small"),
            "Time Mode":        st.column_config.TextColumn("Time Mode", width="small"),
        },
    )
    st.caption("'+1d' means the session ends the following calendar day in that timezone.")
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm & Generate", type="primary", use_container_width=True):
            st.session_state.tz_confirmed = True
            st.rerun()
    with c2:
        if st.button("✖ Cancel", use_container_width=True):
            st.session_state.pending_generate = False
            st.rerun()


# ── Lookup maps ───────────────────────────────────────────────────────────────

course_names   = [c["name"] for c in COURSES]
country_names  = [c["name"] for c in COUNTRIES]
tier_map       = {t["name"]: t for t in PRICING_TIERS}
country_map    = {c["name"]: c for c in COUNTRIES}
course_map     = {c["name"]: c for c in COURSES}
mode_labels    = [m["label"] for m in TRAINING_MODES]
mode_value_map = {m["label"]: m["value"] for m in TRAINING_MODES}


# ── Shared settings ───────────────────────────────────────────────────────────

st.markdown('<p class="section-header">Pricing Tiers (leave unchecked for base price only)</p>', unsafe_allow_html=True)
tier_cols = st.columns(3)
with tier_cols[0]:
    use_bronze = st.checkbox("Bronze", value=True, key="tier_bronze")
with tier_cols[1]:
    use_silver = st.checkbox("Silver", value=True, key="tier_silver")
with tier_cols[2]:
    use_gold   = st.checkbox("Gold",   value=True, key="tier_gold")

col_l, col_r = st.columns(2)
with col_l:
    default_capacity = st.number_input("Default Capacity *", min_value=1, max_value=500, value=20)

col_l, col_r = st.columns(2)
with col_l:
    selected_mode_label = st.selectbox("Training Mode *", mode_labels, index=0)
with col_r:
    selected_status = st.selectbox("Default Status *", STATUSES, index=0)

st.markdown("---")

# ── Bulk Import ───────────────────────────────────────────────────────────────

st.markdown("### Bulk Import")

# Template download
_bulk_template_cols = [
    "Course Name", "Hours Per Day", "Weeks", "Batch Type",
    "Schedule Details", "Toral Training Duration",
    "Start Time", "End Time", "Time Zone", "Start Date", "End Date",
]
st.download_button(
    "⬇ Download Template (CSV)",
    data=(",".join(_bulk_template_cols) + "\n").encode(),
    file_name="bulkimport_template.csv",
    mime="text/csv",
)

# File uploader
bulk_upload = st.file_uploader(
    "Upload Bulk Schedule CSV or Excel",
    type=["csv", "xlsx", "xls"],
    key="bulk_csv_upload",
)

if bulk_upload is not None:
    try:
        if bulk_upload.name.endswith((".xlsx", ".xls")):
            _bulk_df = pd.read_excel(bulk_upload)
        else:
            _bulk_df = pd.read_csv(bulk_upload)
        _parsed_configs, _parsed_warnings = parse_bulk_csv(_bulk_df)
        st.session_state.bulk_configs  = _parsed_configs
        st.session_state.bulk_warnings = _parsed_warnings
    except Exception as _exc:
        st.error(f"Could not parse bulk import file: {_exc}")
        st.session_state.bulk_configs  = []
        st.session_state.bulk_warnings = []

st.markdown("---")

# Date range
st.markdown('<p class="section-header">Schedule Date Range *</p>', unsafe_allow_html=True)
_bd_l, _bd_r = st.columns(2)
with _bd_l:
    bulk_from_date = st.date_input("From Date", value=date(2026, 5, 1), key="bulk_from_date")
with _bd_r:
    bulk_to_date = st.date_input("To Date", value=date(2026, 12, 31), key="bulk_to_date")

# Countries
bulk_selected_countries = st.multiselect(
    "Countries *",
    country_names,
    key="bulk_country_select",
)

bulk_usd_us = st.multiselect(
    "Keep USD pricing & US timezone for",
    options=bulk_selected_countries,
    default=[],
    help="These countries will use USD pricing (rate = 1) and America/New_York time.",
    key="bulk_usd_us",
)

st.markdown('<p class="section-header">Use original time slot (no timezone conversion)</p>', unsafe_allow_html=True)
st.caption(
    "Toggle ON for a country to keep the same wall-clock times as the input "
    "(e.g. 9:00 AM–5:00 PM IST instead of converting from EST). "
    "Currency and pricing still use each country's own rates."
)
bulk_keep_times = st.multiselect(
    "Apply fixed time slot for",
    options=[c for c in bulk_selected_countries if c not in bulk_usd_us],
    default=[k for k in st.session_state.bulk_keep_times
             if k in bulk_selected_countries and k not in bulk_usd_us],
    key="bulk_keep_times",
    label_visibility="collapsed",
)

# Warnings from CSV parse
for _w in st.session_state.bulk_warnings:
    st.warning(_w)

# Course mapping for unrecognised names
if st.session_state.bulk_configs:
    _unique_bulk_courses = list(
        dict.fromkeys(cfg["course_name"] for cfg in st.session_state.bulk_configs)
    )
    _unmapped = [n for n in _unique_bulk_courses if n not in course_map]

    if _unmapped:
        st.markdown("**Course Mapping** — map unrecognised course names to known courses:")
        _skip_label = "(skip)"
        _map_options = [_skip_label] + course_names
        for _cname in _unmapped:
            _current = st.session_state.bulk_course_map.get(_cname, _skip_label)
            _idx = _map_options.index(_current) if _current in _map_options else 0
            _sel = st.selectbox(
                f'Map "{_cname}" to:',
                _map_options,
                index=_idx,
                key=f"bulk_map_{_cname}",
            )
            if _sel == _skip_label:
                st.session_state.bulk_course_map.pop(_cname, None)
            else:
                st.session_state.bulk_course_map[_cname] = _sel

    # Preview table
    _preview_rows = [
        {
            "Course":      cfg["course_name"],
            "Hrs/Day":     cfg["hours_per_day"],
            "Sessions":    cfg["training_days"],
            "Batch Type":  cfg["batch_type"],
            "Weeks":       cfg["weeks_raw"],
            "Day Pattern": cfg["schedule_raw"],
            "Start Time":  to_12h(cfg["start_time"]),
            "End Time":    to_12h(cfg["end_time"]),
        }
        for cfg in st.session_state.bulk_configs
    ]
    if _preview_rows:
        st.dataframe(pd.DataFrame(_preview_rows), use_container_width=True, hide_index=True)
        _n_c = len(dict.fromkeys(cfg["course_name"] for cfg in st.session_state.bulk_configs))
        st.caption(
            f"{len(st.session_state.bulk_configs)} configurations · {_n_c} unique courses"
        )

st.markdown("---")

# ── Exchange Rates ────────────────────────────────────────────────────────────

st.markdown("### Exchange Rates")

src_col, fetch_col, reset_col = st.columns([3, 1.2, 1.2])
with src_col:
    _badge = f"**Source:** {st.session_state.rates_source}"
    if st.session_state.rates_fetched_at:
        _badge += f"  ·  fetched at {st.session_state.rates_fetched_at} UTC"
    st.markdown(_badge)
with fetch_col:
    if st.button("🔄 Fetch Live Rates", use_container_width=True):
        with st.spinner("Fetching…"):
            try:
                live = _fetch_live_rates()
                new_rates = dict(st.session_state.base_rates)
                for c in COUNTRIES:
                    if c["currency"] in live:
                        new_rates[c["currency"]] = round(live[c["currency"]], 4)
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

st.markdown('<p class="section-header">Adjust all rates by a percentage</p>', unsafe_allow_html=True)
adj_l, adj_r, _ = st.columns([1.5, 1, 5])
with adj_l:
    adj_pct = st.number_input(
        "Adjustment (%)", value=0.0, step=0.5, format="%.2f",
        label_visibility="collapsed", key="adj_pct",
    )
    st.caption("e.g. +5 or -3")
with adj_r:
    if st.button("Apply ±%", use_container_width=True):
        new_rates = {
            cur: round(rate * (1 + adj_pct / 100), 4) if rate is not None else None
            for cur, rate in st.session_state.base_rates.items()
        }
        _bump_rates(new_rates, f"{st.session_state.rates_source} ({adj_pct:+.2f}%)")
        st.rerun()

# Rate table for selected countries
rate_rows = []
for name in bulk_selected_countries:
    c    = country_map[name]
    rate = st.session_state.base_rates.get(c["currency"], c["exchange_rate"])
    rate_rows.append({
        "Country":                name,
        "Currency":               c["currency"],
        "Exchange Rate (vs USD)": rate,
    })

df_rates = pd.DataFrame(rate_rows) if rate_rows else pd.DataFrame(
    columns=["Country", "Currency", "Exchange Rate (vs USD)"]
)

editor_key = f"rate_editor_v{st.session_state.rates_version}"
edited_rates_df = st.data_editor(
    df_rates,
    key=editor_key,
    column_config={
        "Country":  st.column_config.TextColumn("Country",  disabled=True),
        "Currency": st.column_config.TextColumn("Currency", disabled=True),
        "Exchange Rate (vs USD)": st.column_config.NumberColumn(
            "Exchange Rate (vs USD)", format="%.4f", min_value=0.0,
        ),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
)

# Persist inline edits back to base_rates
if not edited_rates_df.empty:
    for _, row in edited_rates_df.iterrows():
        val = row["Exchange Rate (vs USD)"]
        st.session_state.base_rates[row["Currency"]] = float(val) if pd.notna(val) else None

st.markdown("---")

# ── Generate & Download ───────────────────────────────────────────────────────

col_btn, _ = st.columns([1, 6])
with col_btn:
    if st.button("⬇ Generate & Download", type="primary", use_container_width=True):
        st.session_state.pending_generate = True
        st.session_state.tz_confirmed = False

if st.session_state.pending_generate:
    bulk_ready = len(st.session_state.bulk_configs) > 0

    # ── Validation ────────────────────────────────────────────────────────────
    errors = []
    selected_tiers = []
    if use_bronze: selected_tiers.append(tier_map["Bronze"])
    if use_silver: selected_tiers.append(tier_map["Silver"])
    if use_gold:   selected_tiers.append(tier_map["Gold"])
    if not selected_tiers:
        errors.append("Select at least one pricing tier.")
    if not bulk_ready:
        errors.append("Upload a bulk import CSV or Excel file first.")
    if not bulk_selected_countries:
        errors.append("Select at least one country.")
    if bulk_from_date >= bulk_to_date:
        errors.append("From Date must be before To Date.")

    if errors:
        for e in errors:
            st.error(e)
        st.session_state.pending_generate = False

    elif not st.session_state.tz_confirmed:
        # ── Build timezone preview ─────────────────────────────────────────
        _preview_countries = [country_map[n] for n in bulk_selected_countries]

        _cfg0 = st.session_state.bulk_configs[0]
        _preview_start = _cfg0["start_time"]
        _preview_end   = _cfg0["end_time"]

        _unique_times = list(dict.fromkeys(
            (cfg["start_time"], cfg["end_time"])
            for cfg in st.session_state.bulk_configs
        ))
        _bulk_note = None
        if len(_unique_times) > 1:
            _time_list = ", ".join(
                f"{to_12h(s)}–{to_12h(e)}" for s, e in _unique_times[:4]
            ) + ("…" if len(_unique_times) > 4 else "")
            _bulk_note = (
                f"Import has **{len(_unique_times)} different time slots** "
                f"({_time_list}). Preview shows the first; all convert correctly."
            )

        _tz_rows = compute_tz_preview(
            _preview_countries,
            _preview_start,
            _preview_end,
            bulk_from_date,
            bulk_usd_us,
            bulk_keep_times,
        )
        _tz_preview_dialog(
            _tz_rows,
            to_12h(_preview_start),
            to_12h(_preview_end),
            bulk_from_date.strftime("%d %b %Y"),
            _bulk_note,
        )

    else:
        # ── Confirmed — run generation ─────────────────────────────────────
        st.session_state.pending_generate = False
        st.session_state.tz_confirmed = False

        selected_tiers = []
        if use_bronze: selected_tiers.append(tier_map["Bronze"])
        if use_silver: selected_tiers.append(tier_map["Silver"])
        if use_gold:   selected_tiers.append(tier_map["Gold"])

        # Rate lookup from edited table
        rate_lookup: dict[str, float | None] = {}
        if not edited_rates_df.empty:
            for _, row in edited_rates_df.iterrows():
                val = row["Exchange Rate (vs USD)"]
                rate_lookup[row["Country"]] = float(val) if pd.notna(val) else None

        countries_with_rates = []
        for name in bulk_selected_countries:
            c = dict(country_map[name])
            c["exchange_rate"] = rate_lookup.get(name, c["exchange_rate"])
            countries_with_rates.append(c)

        course_id_map = {}
        for cfg in st.session_state.bulk_configs:
            name = cfg["course_name"]
            if name in course_map:
                course_id_map[name] = course_map[name]["id"]
            else:
                mapped = st.session_state.bulk_course_map.get(name)
                course_id_map[name] = course_map[mapped]["id"] if mapped and mapped in course_map else 0

        bulk_shared = {
            "pricing_tiers":        selected_tiers,
            "default_capacity":     int(default_capacity),
            "training_mode":        mode_value_map[selected_mode_label],
            "status":               selected_status,
            "countries":            countries_with_rates,
            "usd_us_countries":     bulk_usd_us,
            "keep_times_countries": bulk_keep_times,
            "course_id_map":        course_id_map,
            "override_from_date":   bulk_from_date,
            "override_to_date":     bulk_to_date,
        }

        with st.spinner("Generating schedules…"):
            all_rows = generate_schedules_bulk(st.session_state.bulk_configs, bulk_shared)

        if not all_rows:
            st.warning("No schedules generated. Check your date range and batch settings.")
        else:
            xlsx_bytes = rows_to_excel_bytes(all_rows)
            filename   = f"bulk-schedules-{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
            st.success(f"Generated **{len(all_rows)}** rows.")
            st.download_button(
                label="⬇ Download Excel",
                data=xlsx_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
            with st.expander("Preview (first 50 rows)", expanded=False):
                st.dataframe(pd.DataFrame(all_rows[:50]), use_container_width=True)
