from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import json

from data import DAY_TO_US_DOW, COURSE_PRICING

_INPUT_TZ = "America/New_York"


def _convert_time(time_str: str, to_tz: str, ref_date: date) -> str:
    """
    Convert HH:MM from America/New_York to `to_tz` using `ref_date` for DST accuracy.
    Returns the original string unchanged when target is already New York.
    """
    if to_tz == _INPUT_TZ:
        return time_str
    h, m = map(int, time_str.split(":"))
    dt = datetime(ref_date.year, ref_date.month, ref_date.day, h, m,
                  tzinfo=ZoneInfo(_INPUT_TZ))
    return dt.astimezone(ZoneInfo(to_tz)).strftime("%H:%M")


def _nth_day_of_month(year: int, month: int, anchor_us_dow: int, n: int) -> date | None:
    """
    Return the n-th occurrence of anchor_us_dow (US convention: Sun=0 … Sat=6)
    in the given month, or None if the month has fewer than n occurrences.
    """
    first_day = date(year, month, 1)
    first_us_dow = (first_day.weekday() + 1) % 7          # Python Mon=0 → US Sun=0
    days_ahead = (anchor_us_dow - first_us_dow) % 7
    result = first_day + timedelta(days=days_ahead) + timedelta(weeks=n - 1)
    return result if result.month == month else None


def _batch_dates_for_type(
    batch_type: str,
    day_format: list[str],
    weeks: list[int],
    from_date: date,
    to_date: date,
    training_days: int,
) -> list[tuple[date, date, list[date]]]:
    """
    Return list of (start, end, sessions) tuples for the given batch type.

    Anchor logic:
    - weekday: W_n = n-th Monday of the month; batch starts on that Monday.
    - weekend: W_n = n-th Saturday of the month; batch starts on the first
      day of day_format relative to that Saturday (e.g. Friday before it
      when format begins on Fri).

    A batch is skipped when its first session falls outside the current
    calendar month or outside [from_date, to_date].
    """
    if not day_format or not weeks:
        return []

    first_us_dow = DAY_TO_US_DOW[day_format[0]]

    if batch_type == "weekday":
        anchor_us_dow = DAY_TO_US_DOW["Mon"]   # always anchor on Monday
        start_offset = 0                        # batch starts on the Monday itself
    else:
        anchor_us_dow = DAY_TO_US_DOW["Sat"]   # always anchor on Saturday
        start_offset = first_us_dow - anchor_us_dow  # e.g. Fri(5)-Sat(6) = -1

    batches: list[tuple[date, date, list[date]]] = []

    current = from_date.replace(day=1)
    while current <= to_date.replace(day=1):
        year, month = current.year, current.month

        for week_num in sorted(weeks):
            anchor_date = _nth_day_of_month(year, month, anchor_us_dow, week_num)
            if anchor_date is None:
                continue

            first_session = anchor_date + timedelta(days=start_offset)

            # Skip if first session fell into the previous month
            if first_session.month != month:
                continue
            if first_session < from_date:
                continue

            sessions = [first_session + timedelta(days=i) for i in range(training_days)]

            if sessions[-1] > to_date:
                continue

            batches.append((sessions[0], sessions[-1], sessions))

        current = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    return batches


def _calc_final_price(base_price: int, tier_pct: int, exchange_rate) -> float | None:
    if exchange_rate is None:
        return None
    return round(base_price * (1 + tier_pct / 100) * exchange_rate, 2)


def generate_schedules(params: dict) -> list[dict]:
    """
    Generate schedule rows from form params.

    Expected keys in `params`:
        course_id, course_name,
        from_date (date), to_date (date),
        pricing_tiers (list of tier dicts),
        training_days (int), default_capacity (int),
        weekday_batches_enabled (bool),
        weekday_day_format (list[str]), weekday_weeks (list[int]),
        weekend_batches_enabled (bool),
        weekend_day_format (list[str]), weekend_weeks (list[int]),
        training_mode (str), start_time (str), end_time (str),
        duration (int), status (str),
        countries (list of country dicts),

    Returns list of row dicts matching Excel column names.
    """
    weekday_batches = (
        _batch_dates_for_type(
            "weekday",
            params["weekday_day_format"],
            params["weekday_weeks"],
            params["from_date"],
            params["to_date"],
            params["training_days"],
        )
        if params.get("weekday_batches_enabled")
        else []
    )

    weekend_batches = (
        _batch_dates_for_type(
            "weekend",
            params["weekend_day_format"],
            params["weekend_weeks"],
            params["from_date"],
            params["to_date"],
            params["training_days"],
        )
        if params.get("weekend_batches_enabled")
        else []
    )

    # Group batches by month so we can interleave weekday then weekend per month
    def _by_month(batches):
        months: dict[tuple, list] = {}
        for b in batches:
            key = (b[0].year, b[0].month)
            months.setdefault(key, []).append(b)
        return months

    wd_by_month = _by_month(weekday_batches)
    we_by_month = _by_month(weekend_batches)
    all_months = sorted(set(list(wd_by_month) + list(we_by_month)), reverse=True)

    rows: list[dict] = []

    # Countries that keep USD pricing and New York timezone
    usd_us_countries: set[str] = set(params.get("usd_us_countries", []))

    for country in params["countries"]:
        base_price = COURSE_PRICING.get(
            (params["course_id"], country["region"]), 995
        )

        # Apply USD / US-timezone override if requested
        use_usd_us = country["name"] in usd_us_countries
        eff_timezone    = _INPUT_TZ              if use_usd_us else country["timezone"]
        eff_currency    = "USD"                  if use_usd_us else country["currency"]
        eff_exch_rate   = 1.0                    if use_usd_us else country["exchange_rate"]

        for month_key in all_months:
            for batch_type, batch_group in [
                ("weekday", wd_by_month.get(month_key, [])),
                ("weekend", we_by_month.get(month_key, [])),
            ]:
                for start, end, sessions in sorted(batch_group, key=lambda b: b[0], reverse=True):
                    sessions_json = json.dumps(
                        [s.strftime("%Y-%m-%d") for s in sessions]
                    )
                    # Convert times using the batch start date for correct DST
                    local_start_time = _convert_time(
                        params["start_time"], eff_timezone, start
                    )
                    local_end_time = _convert_time(
                        params["end_time"], eff_timezone, start
                    )

                    for tier in params["pricing_tiers"]:
                        final_price = _calc_final_price(
                            base_price, tier["percentage"], eff_exch_rate
                        )
                        rows.append({
                            "Course ID":            params["course_id"],
                            "Course Name":          params["course_name"],
                            "Country ID":           country["id"],
                            "Country":              country["name"],
                            "Region":               country["region"],
                            "Pricing Tier ID":      tier["id"],
                            "Pricing Tier":         tier["name"],
                            "Duration (hr)":        params["duration"],
                            "Batch Type":           batch_type,
                            "Start Date":           start.strftime("%Y-%m-%d"),
                            "End Date":             end.strftime("%Y-%m-%d"),
                            "Session Dates (JSON)": sessions_json,
                            "Start Time":           local_start_time,
                            "End Time":             local_end_time,
                            "Timezone":             eff_timezone,
                            "Capacity":             params["default_capacity"],
                            "Base Price USD":        base_price,
                            "Tier %":               tier["percentage"],
                            "Exchange Rate":         eff_exch_rate,
                            "Final Price":           final_price,
                            "Currency":              eff_currency,
                            "Training Mode":         params["training_mode"],
                            "Status":                params["status"].lower(),
                            "Generation Result":     "new",
                            "Error Message":         None,
                            "Price Override Flag":   "false",
                            "Override Reason":       None,
                        })

    return rows


def rows_to_excel_bytes(rows: list[dict]) -> bytes:
    """Serialize schedule rows to an xlsx file and return as bytes."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    COLUMNS = [
        "Course ID", "Course Name", "Country ID", "Country", "Region",
        "Pricing Tier ID", "Pricing Tier", "Duration (hr)", "Batch Type",
        "Start Date", "End Date", "Session Dates (JSON)", "Start Time",
        "End Time", "Timezone", "Capacity", "Base Price USD", "Tier %",
        "Exchange Rate", "Final Price", "Currency", "Training Mode",
        "Status", "Generation Result", "Error Message",
        "Price Override Flag", "Override Reason",
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9D9D9")

    for col_idx, col_name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, col_name in enumerate(COLUMNS, start=1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(col_name))

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
