# Bulk Import Schedule Generator — Implementation Plan

## 1. What the Feature Does

A user uploads a CSV (like `bulkimport.csv`) that defines **every combination of course duration,
batch type, and day pattern** they want to generate schedules for.  The app pairs each row in that
CSV with the countries, pricing tiers, and exchange rates already configured in the form, then
produces one large Excel output covering all combinations.

---

## 2. CSV Format Analysis

### Observed columns

| Column | Example values | Role |
|---|---|---|
| `Course Name` | PgMP | Maps to a course in the system |
| `Hours Per Day` | 8, 6, 4, 3 | Daily session length; drives End Time and training-day count |
| `Weeks` | `1 week`, `1-2 Week`, `3-4-5 week` | Which week(s) of the month batches start in |
| `Batch Type` | Weekday, Weekend, Combined | Drives anchor-day selection |
| `Schedule Details` | `Mon, Tue, Wed` / `Sat, Sun, Sat` | Ordered list of session days (may repeat / span weeks) |
| `Toral Training Duration` | 24 (constant) | Total contact hours |
| `Start Time` | `9:00 AM` | Input in EST; converted per country |
| `End Time` | `5:00 PM` | Input in EST; converted per country |
| `Time Zone` | EST | Always EST (input reference) |
| `Start Date` | `01-May-2026` | Range start for all batches in this row |
| `End Date` | `31-December-2026` | Range end |

### Derived values

| Derived field | Formula | Example |
|---|---|---|
| Training days (sessions) | `Total Duration ÷ Hours Per Day` | 24 ÷ 8 = **3**, 24 ÷ 6 = **4**, 24 ÷ 4 = **6**, 24 ÷ 3 = **8** |
| Session day list | Split `Schedule Details` on `, ` | `["Mon","Tue","Wed"]` |
| Starting week numbers | Extract digits from `Weeks` | `"1-2 Week"` → `[1, 2]` |
| Start/End time (24 h) | Parse AM/PM string | `"9:00 AM"` → `"09:00"` |

---

## 3. Column Parsing Rules

### 3a. `Weeks` → list of week numbers

Strip non-digit characters, split on `-`, cast to int.

```
"1 week"        → [1]
"1-2 Week"      → [1, 2]
"3-4 Week"      → [3, 4]
"2-3 week"      → [2, 3]
"1-2-3 Weekend" → [1, 2, 3]
"1-2-3-4 Week"  → [1, 2, 3, 4]
"3-4-5 week"    → [3, 4, 5]
"5 Week"        → [5]
```

### 3b. `Schedule Details` → ordered day list

Split on `, ` (comma-space).  Days may repeat across weeks (e.g. `Sat, Sun, Sat`).

### 3c. `Start Time` / `End Time` → 24-hour string

Parse with `datetime.strptime(value, "%I:%M %p")` → `.strftime("%H:%M")`.

### 3d. Anchor-day selection (determines session start date)

The **anchor** is the calendar day used to locate week N in a month.

| Batch Type | Anchor day |
|---|---|
| Weekday | First day in `Schedule Details` (typically Mon) |
| Weekend | First day in `Schedule Details` (typically Sat) |
| Combined | First day in `Schedule Details` (e.g. Fri, Mon, Thu — whatever starts the run) |

> This unifies all three types under one rule: _anchor = first element of Schedule Details_.

Current app logic (Mon anchor for weekday, Sat for weekend) is a special case of this general rule.

### 3e. Session date generation from anchor

Given anchor date `A` and day sequence `[d0, d1, d2, …]`:

```
sessions[0] = A                          # anchor date, already on d0
sessions[i] = next_occurrence(sessions[i-1], d_i)   # first date > prev on day d_i
```

`next_occurrence(base, target_dow)`:
- delta = (target_us_dow − base_us_dow) % 7
- if delta == 0: delta = 7   ← always move forward
- return base + timedelta(days=delta)

Example — `Sat, Sun, Sat` anchored on Sat 2 May:
```
sessions[0] = May 2  (Sat)
sessions[1] = next Sun after May 2  = May 3
sessions[2] = next Sat after May 3  = May 9
→ [May 2, May 3, May 9]
```

Example — `Mon, Tue, Wed, Thu, Fri, Mon` anchored on Mon 4 May:
```
[May 4, May 5, May 6, May 7, May 8, May 11]
```

---

## 4. Schedule Generation Algorithm

```
for each CSV row R:
    parse → anchor_dow, week_numbers, sessions_template, start_time, end_time, date_range

    for each month M in date_range:
        for each week_num W in week_numbers:
            anchor_date = Nth occurrence of anchor_dow in month M
            if anchor_date is None or anchor_date < from_date: skip

            sessions = generate_sessions(anchor_date, sessions_template)
            if any session > to_date: skip

            for each selected Country C:
                eff_timezone  = US TZ  if C in usd_us_countries else C.timezone
                eff_currency  = USD    if C in usd_us_countries else C.currency
                eff_exch_rate = 1.0    if C in usd_us_countries else rate_from_table[C]
                local_start   = convert_time(start_time, eff_timezone, anchor_date)
                local_end     = convert_time(end_time,   eff_timezone, anchor_date)

                for each Pricing Tier T:
                    final_price = base_price × (1 + T.pct/100) × eff_exch_rate
                    emit row → Excel
```

Row order (descending by start date, same as current behaviour):
`month desc → batch_type (Weekday first) → batch asc → tier`

---

## 5. UI Changes Required

### 5a. New "Bulk Import" tab / section

Add a tab or expander **"Bulk Import Courses"** alongside the existing manual form.

**Controls:**
- File uploader accepting `.csv` / `.xlsx` — the course-schedule definitions file
- "Download Template" button — generates a filled template matching `bulkimport.csv` structure
- Preview table showing parsed rows (Course, Duration, Batch Type, Weeks, Day Pattern, Sessions)
- Validation warnings for unrecognised course names, unparseable times, bad week strings

### 5b. Course lookup / creation

When a CSV row contains a `Course Name` not in `data.COURSES`, two options:
1. **Warn and skip** (safe default)
2. **Auto-add** to in-memory course list for this session

Plan: warn and highlight unrecognised courses; allow user to map them to an existing course via a dropdown before generating.

### 5c. Shared country / pricing / exchange-rate settings

The bulk import reuses **all existing form settings** (countries, pricing tiers, exchange rates, USD
override list, training mode, default capacity, default status).  Only the course-level fields
come from the CSV.

### 5d. Generate button behaviour

- If both manual rows and bulk-import rows are present, combine into one Excel output.
- Show a summary: `N courses × M countries × P tiers × Q batches = R total rows`.

---

## 6. Output Format

Same 27-column Excel schema as current output. Multi-course runs produce all rows in one sheet,
sorted: **course → country → month desc → batch → tier**.

Additional consideration: add a **`Course Duration (hr/day)`** column (col 28) so the output
makes clear which duration variant each row belongs to.

---

## 7. Implementation Steps

| Step | File(s) | What changes |
|---|---|---|
| 1 | `data.py` | Add PgMP and any other CSV courses to `COURSES` and `COURSE_PRICING` |
| 2 | `generator.py` | Generalise `_batch_dates_for_type` to accept an arbitrary anchor day and a day sequence instead of a fixed 3-consecutive-day pattern |
| 3 | `generator.py` | Add `generate_sessions_from_sequence(anchor, day_sequence)` using the next-occurrence algorithm |
| 4 | `generator.py` | Add `parse_bulk_csv(file)` → list of normalised config dicts |
| 5 | `generator.py` | Add `generate_schedules_bulk(csv_rows, shared_params)` that loops CSV rows and calls the updated core |
| 6 | `app.py` | Add "Bulk Import" expander with uploader, preview, and mapping UI |
| 7 | `app.py` | Wire "Generate & Download" to merge manual + bulk rows |
| 8 | `requirements.txt` | No new deps needed (`zoneinfo`, `pandas`, `openpyxl` already present) |

---

## 8. Edge Cases & Constraints

| Case | Handling |
|---|---|
| Session spans midnight (e.g. start 10 PM, end 6 AM next day) | End time < start time → mark end as next-day in output; add `+1d` note in End Time cell |
| Week N doesn't exist in a short month (e.g. W5 in February) | `_nth_day_of_month` returns `None` → skip silently |
| First session of anchor falls before `from_date` | Skip that batch |
| Last session exceeds `to_date` | Skip that batch |
| Duplicate rows in CSV (same course + duration + weeks + days) | Deduplicate before generating to avoid double rows |
| CSV course name doesn't match any in system | Surface warning in UI; skip or allow manual mapping |
| Mixed `Time Zone` values in CSV (not all EST) | Parse TZ column; currently only EST is supported — warn if other values present |
| `Hours Per Day` of 2 or 1 (below the "more than 1 hr" minimum) | Validate on import: reject rows where `Hours Per Day ≤ 1` |
| Very large outputs (20 countries × 5 courses × 3 tiers × 50 batches = 15,000+ rows) | Stream to Excel rather than building full list in memory; show progress bar in UI |
