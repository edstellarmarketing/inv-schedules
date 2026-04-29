"""Bulk Schedule Generator – Streamlit app."""

from datetime import date, datetime, time
import io as _io
import pandas as pd
import requests
import streamlit as st

from data import (
    COURSES, COUNTRIES, COURSE_PRICING, PRICING_TIERS,
    TRAINING_MODES, STATUSES, DAYS_OF_WEEK,
)
from generator import (
    generate_schedules, generate_schedules_bulk, parse_bulk_csv,
    rows_to_excel_bytes, compute_tz_preview, to_12h,
)


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
if "country_select" not in st.session_state:
    st.session_state["country_select"] = _DEFAULT_COUNTRIES

if "bulk_country_select" not in st.session_state:
    st.session_state["bulk_country_select"] = _DEFAULT_COUNTRIES

if "bulk_configs" not in st.session_state:
    st.session_state.bulk_configs = []
if "bulk_warnings" not in st.session_state:
    st.session_state.bulk_warnings = []
if "bulk_course_map" not in st.session_state:
    st.session_state.bulk_course_map = {}

if "pending_generate" not in st.session_state:
    st.session_state.pending_generate = False
if "tz_confirmed" not in st.session_state:
    st.session_state.tz_confirmed = False


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
            "USD Override":     st.column_config.TextColumn("USD Override", width="small"),
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

course_names    = [c["name"] for c in COURSES]
country_names   = [c["name"] for c in COUNTRIES]
tier_map        = {t["name"]: t for t in PRICING_TIERS}
country_map     = {c["name"]: c for c in COUNTRIES}
course_map      = {c["name"]: c for c in COURSES}
mode_labels     = [m["label"] for m in TRAINING_MODES]
mode_value_map  = {m["label"]: m["value"] for m in TRAINING_MODES}


# ── Shared: Pricing Tiers, Capacity, Training Mode, Status ───────────────────

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

# ── Tabs: Manual Schedule | Bulk Import ──────────────────────────────────────

tab_manual, tab_bulk = st.tabs(["📋 Manual Schedule", "📂 Bulk Import"])

# ── Tab: Manual Schedule ──────────────────────────────────────────────────────

with tab_manual:
    col_l, col_r = st.columns(2)
    with col_l:
        selected_course_name = st.selectbox("Course *", course_names, index=0)
    with col_r:
        selected_country_names = st.multiselect(
            "Countries *",
            country_names,
            key="country_select",
        )

    usd_us_countries = st.multiselect(
        "Keep USD pricing & US timezone for",
        options=selected_country_names,
        default=[],
        help="Selected countries will show prices in USD (exchange rate = 1) and times in "
             "America/New_York instead of their local timezone.",
    )

    with st.expander("📎 Bulk Upload Countries"):
        up_l, up_r = st.columns([3, 1])
        with up_r:
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
                _col = next(
                    (c for c in _df_up.columns if c.strip().lower() == "country"),
                    _df_up.columns[0],
                )
                _raw = _df_up[_col].dropna().str.strip().tolist()
                _valid_set    = set(country_names)
                _recognised   = [n for n in _raw if n in _valid_set]
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

    st.markdown("---")

    col_l, col_r = st.columns(2)
    with col_l:
        from_date = st.date_input("From Date *", value=date(2026, 5, 1))
    with col_r:
        to_date = st.date_input("To Date *", value=date(2026, 8, 31))

    col_l, _ = st.columns(2)
    with col_l:
        training_days = st.number_input(
            "Training Days (same for weekday & weekend) *",
            min_value=1, max_value=30, value=3,
        )

    st.markdown("---")

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

    st.markdown('<p class="section-header">Time Slots (enter in New York EST; stored in each country\'s local timezone) *</p>', unsafe_allow_html=True)
    ts_l, ts_r = st.columns(2)
    with ts_l:
        start_time_val = st.time_input("Start time *", value=time(9, 0),  key="start_time")
    with ts_r:
        end_time_val   = st.time_input("End time *",   value=time(17, 0), key="end_time")

    col_l, _ = st.columns(2)
    with col_l:
        duration = st.number_input("Duration (hours) *", min_value=1, max_value=24, value=8)


# ── Tab: Bulk Import ──────────────────────────────────────────────────────────

with tab_bulk:
    # Template download
    _bulk_template_cols = [
        "Course Name", "Hours Per Day", "Weeks", "Batch Type",
        "Schedule Details", "Toral Training Duration",
        "Start Time", "End Time", "Time Zone", "Start Date", "End Date",
    ]
    _template_csv = ",".join(_bulk_template_cols) + "\n"
    st.download_button(
        "⬇ Download Bulk Import Template (CSV)",
        data=_template_csv.encode(),
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

    # Date range (required)
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
        help="Selected countries will show prices in USD (exchange rate = 1) and times in "
             "America/New_York instead of their local timezone.",
        key="bulk_usd_us",
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

        # Preview table (no date columns — dates come from UI above)
        _preview_rows = []
        for _cfg in st.session_state.bulk_configs:
            _preview_rows.append({
                "Course":      _cfg["course_name"],
                "Hrs/Day":     _cfg["hours_per_day"],
                "Sessions":    _cfg["training_days"],
                "Batch Type":  _cfg["batch_type"],
                "Weeks":       _cfg["weeks_raw"],
                "Day Pattern": _cfg["schedule_raw"],
                "Start Time":  _cfg["start_time"],
                "End Time":    _cfg["end_time"],
            })

        if _preview_rows:
            st.dataframe(pd.DataFrame(_preview_rows), use_container_width=True, hide_index=True)
            _n_configs = len(st.session_state.bulk_configs)
            _n_courses = len(dict.fromkeys(cfg["course_name"] for cfg in st.session_state.bulk_configs))
            st.caption(f"{_n_configs} configurations · {_n_courses} unique courses")

st.markdown("---")

# ── Exchange Rates ────────────────────────────────────────────────────────────

st.markdown("### Exchange Rates")

src_col, fetch_col, reset_col = st.columns([3, 1.2, 1.2])
with src_col:
    src_label  = st.session_state.rates_source
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

st.markdown('<p class="section-header">Adjust all rates by a percentage</p>', unsafe_allow_html=True)
adj_l, adj_r, _ = st.columns([1.5, 1, 5])
with adj_l:
    adj_pct = st.number_input(
        "Adjustment (%)", value=0.0, step=0.5, format="%.2f",
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

# Rate table — union of manual + bulk countries
course_obj = course_map[selected_course_name]

def _bronze_preview(country_obj, rate):
    if rate is None:
        return None
    base = COURSE_PRICING.get((course_obj["id"], country_obj["region"]), 995)
    bronze_pct = PRICING_TIERS[0]["percentage"]
    return round(base * (1 + bronze_pct / 100) * rate, 2)

_rate_country_names = list(dict.fromkeys(
    list(selected_country_names) + list(bulk_selected_countries)
))

rate_rows = []
for name in _rate_country_names:
    c    = country_map[name]
    rate = st.session_state.base_rates.get(c["currency"], c["exchange_rate"])
    rate_rows.append({
        "Country":                name,
        "Currency":               c["currency"],
        "Exchange Rate (vs USD)": rate,
        "Bronze Price Preview":   _bronze_preview(c, rate),
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
        ),
        "Bronze Price Preview": st.column_config.NumberColumn(
            "Bronze Price Preview",
            format="%.2f",
            disabled=True,
            help="Base price × 1.15 × exchange rate (Bronze tier, reference only).",
        ),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
)

if not edited_rates_df.empty:
    def _live_bronze(row):
        c = country_map.get(row["Country"])
        if c is None:
            return None
        return _bronze_preview(c, row["Exchange Rate (vs USD)"])
    edited_rates_df["Bronze Price Preview"] = edited_rates_df.apply(_live_bronze, axis=1)

    for _, row in edited_rates_df.iterrows():
        cur = row["Currency"]
        val = row["Exchange Rate (vs USD)"]
        st.session_state.base_rates[cur] = val if pd.notna(val) else None

st.markdown("---")

# ── Generate & Download ───────────────────────────────────────────────────────

col_btn, _ = st.columns([1, 6])
with col_btn:
    if st.button("⬇ Generate & Download", type="primary", use_container_width=True):
        st.session_state.pending_generate = True
        st.session_state.tz_confirmed = False

if st.session_state.pending_generate:
    manual_ready = (wd_batches > 0 or we_batches > 0)
    bulk_ready   = len(st.session_state.bulk_configs) > 0

    # ── Validation ────────────────────────────────────────────────────────────
    errors = []

    selected_tiers = []
    if use_bronze: selected_tiers.append(tier_map["Bronze"])
    if use_silver: selected_tiers.append(tier_map["Silver"])
    if use_gold:   selected_tiers.append(tier_map["Gold"])
    if not selected_tiers:
        errors.append("Select at least one pricing tier.")

    if not manual_ready and not bulk_ready:
        errors.append("Enable at least one of: weekday/weekend batches (Manual tab) or upload a bulk import file (Bulk Import tab).")

    if manual_ready:
        if not selected_country_names:
            errors.append("Manual Schedule: select at least one country.")
        if from_date >= to_date:
            errors.append("Manual Schedule: From Date must be before To Date.")
        if wd_batches > 0 and not wd_day_format: errors.append("Manual Schedule: select at least one weekday day.")
        if wd_batches > 0 and not wd_weeks:      errors.append("Manual Schedule: select at least one weekday week.")
        if we_batches > 0 and not we_day_format: errors.append("Manual Schedule: select at least one weekend day.")
        if we_batches > 0 and not we_weeks:      errors.append("Manual Schedule: select at least one weekend week.")

    if bulk_ready:
        if not bulk_selected_countries:
            errors.append("Bulk Import: select at least one country.")
        if bulk_from_date >= bulk_to_date:
            errors.append("Bulk Import: From Date must be before To Date.")

    if errors:
        for e in errors:
            st.error(e)
        st.session_state.pending_generate = False

    elif not st.session_state.tz_confirmed:
        # ── Build timezone preview and show dialog ─────────────────────────
        # Collect all unique countries for the preview
        _preview_countries = []
        _seen_names: set[str] = set()
        _preview_start = _preview_end = None
        _ref_date_preview = None
        _usd_override: list[str] = []
        _bulk_note = None

        if manual_ready:
            for _n in selected_country_names:
                if _n not in _seen_names:
                    _preview_countries.append(country_map[_n])
                    _seen_names.add(_n)
            _preview_start = time_to_str(start_time_val)
            _preview_end   = time_to_str(end_time_val)
            _ref_date_preview = from_date
            _usd_override = list(usd_us_countries)

        if bulk_ready:
            for _n in bulk_selected_countries:
                if _n not in _seen_names:
                    _preview_countries.append(country_map[_n])
                    _seen_names.add(_n)
            _usd_override = list(dict.fromkeys(_usd_override + list(bulk_usd_us)))

            if _preview_start is None and st.session_state.bulk_configs:
                # Use first config's times as representative
                _c0 = st.session_state.bulk_configs[0]
                _preview_start = _c0["start_time"]
                _preview_end   = _c0["end_time"]
                _ref_date_preview = bulk_from_date

            # Check for multiple distinct time slots in bulk
            _unique_times = list(dict.fromkeys(
                (cfg["start_time"], cfg["end_time"])
                for cfg in st.session_state.bulk_configs
            ))
            if len(_unique_times) > 1:
                _time_list = ", ".join(
                    f"{to_12h(s)}–{to_12h(e)}" for s, e in _unique_times[:4]
                ) + ("…" if len(_unique_times) > 4 else "")
                _bulk_note = (
                    f"Bulk import has **{len(_unique_times)} different time slots** "
                    f"({_time_list}). Preview shows the first; "
                    f"all will be converted correctly on generate."
                )

        if _preview_countries and _preview_start and _ref_date_preview:
            _tz_rows = compute_tz_preview(
                _preview_countries,
                _preview_start,
                _preview_end,
                _ref_date_preview,
                _usd_override,
            )
            _tz_preview_dialog(
                _tz_rows,
                to_12h(_preview_start),
                to_12h(_preview_end),
                _ref_date_preview.strftime("%d %b %Y"),
                _bulk_note,
            )

    else:
        # ── Confirmed — run generation ─────────────────────────────────────
        st.session_state.pending_generate = False
        st.session_state.tz_confirmed = False

        # Rebuild selected_tiers (may not be in scope here; recompute)
        selected_tiers = []
        if use_bronze: selected_tiers.append(tier_map["Bronze"])
        if use_silver: selected_tiers.append(tier_map["Silver"])
        if use_gold:   selected_tiers.append(tier_map["Gold"])

        manual_ready = (wd_batches > 0 or we_batches > 0)
        bulk_ready   = len(st.session_state.bulk_configs) > 0

        # Build rate lookup from edited table
        rate_lookup: dict[str, float | None] = {}
        if not edited_rates_df.empty:
            for _, row in edited_rates_df.iterrows():
                val = row["Exchange Rate (vs USD)"]
                rate_lookup[row["Country"]] = float(val) if pd.notna(val) else None

        def _countries_with_rates(names):
            result = []
            for name in names:
                c = dict(country_map[name])
                c["exchange_rate"] = rate_lookup.get(name, c["exchange_rate"])
                result.append(c)
            return result

        all_rows     = []
        manual_count = 0
        bulk_count   = 0

        if manual_ready:
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
                "countries":               _countries_with_rates(selected_country_names),
                "usd_us_countries":        usd_us_countries,
            }
            with st.spinner("Generating manual schedules…"):
                manual_rows = generate_schedules(params)
            all_rows    += manual_rows
            manual_count = len(manual_rows)

        if bulk_ready:
            course_id_map = {}
            for cfg in st.session_state.bulk_configs:
                name = cfg["course_name"]
                if name in course_map:
                    course_id_map[name] = course_map[name]["id"]
                else:
                    mapped = st.session_state.bulk_course_map.get(name)
                    if mapped and mapped in course_map:
                        course_id_map[name] = course_map[mapped]["id"]
                    else:
                        course_id_map[name] = 0

            bulk_shared = {
                "pricing_tiers":      selected_tiers,
                "default_capacity":   int(default_capacity),
                "training_mode":      mode_value_map[selected_mode_label],
                "status":             selected_status,
                "countries":          _countries_with_rates(bulk_selected_countries),
                "usd_us_countries":   bulk_usd_us,
                "course_id_map":      course_id_map,
                "override_from_date": bulk_from_date,
                "override_to_date":   bulk_to_date,
            }
            with st.spinner("Generating bulk schedules…"):
                bulk_rows = generate_schedules_bulk(st.session_state.bulk_configs, bulk_shared)
            all_rows  += bulk_rows
            bulk_count = len(bulk_rows)

        if not all_rows:
            st.warning("No schedules generated. Check your date range and batch settings.")
        else:
            xlsx_bytes = rows_to_excel_bytes(all_rows)
            filename   = f"bulk-schedules-{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"

            if manual_ready and bulk_ready:
                st.success(
                    f"Generated **{len(all_rows)}** rows — "
                    f"**{manual_count}** from manual schedule, **{bulk_count}** from bulk import."
                )
            elif manual_ready:
                st.success(f"Generated **{len(all_rows)}** rows from manual schedule.")
            else:
                st.success(f"Generated **{len(all_rows)}** rows from bulk import.")

            st.download_button(
                label="⬇ Download Excel",
                data=xlsx_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

            with st.expander("Preview (first 50 rows)", expanded=False):
                st.dataframe(pd.DataFrame(all_rows[:50]), use_container_width=True)
