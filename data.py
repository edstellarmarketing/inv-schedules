COURSES = [
    {"id": 1, "name": "PMP Certification"},
    {"id": 2, "name": "Six Sigma Green Belt"},
    {"id": 3, "name": "PRINCE2 Foundation"},
    {"id": 4, "name": "AWS Cloud Practitioner"},
    {"id": 5, "name": "Agile Scrum Master"},
    {"id": 6, "name": "PgMP"},
]

COUNTRIES = [
    {"id": 1,  "name": "United States",        "region": "Region 1 (Americas/Europe)",       "timezone": "America/New_York",      "currency": "USD", "exchange_rate": 1.0},
    {"id": 2,  "name": "United Kingdom",        "region": "Region 1 (Americas/Europe)",       "timezone": "Europe/London",         "currency": "GBP", "exchange_rate": 0.79},
    {"id": 3,  "name": "Canada",                "region": "Region 1 (Americas/Europe)",       "timezone": "America/Toronto",       "currency": "CAD", "exchange_rate": 1.36},
    {"id": 4,  "name": "Australia",             "region": "Region 1 (Americas/Europe)",       "timezone": "Australia/Sydney",      "currency": "AUD", "exchange_rate": 1.53},
    {"id": 5,  "name": "Germany",               "region": "Region 1 (Americas/Europe)",       "timezone": "Europe/Berlin",         "currency": "EUR", "exchange_rate": 0.92},
    {"id": 6,  "name": "Netherlands",           "region": "Region 1 (Americas/Europe)",       "timezone": "Europe/Amsterdam",      "currency": "EUR", "exchange_rate": 0.92},
    {"id": 7,  "name": "Brazil",                "region": "Region 1 (Americas/Europe)",       "timezone": "America/Sao_Paulo",     "currency": "BRL", "exchange_rate": 4.97},
    {"id": 8,  "name": "New Zealand",           "region": "Region 1 (Americas/Europe)",       "timezone": "Pacific/Auckland",      "currency": "NZD", "exchange_rate": None},
    {"id": 9,  "name": "United Arab Emirates",  "region": "Region 2 (Middle East/East Asia)", "timezone": "Asia/Dubai",            "currency": "AED", "exchange_rate": 3.67},
    {"id": 10, "name": "Singapore",             "region": "Region 2 (Middle East/East Asia)", "timezone": "Asia/Singapore",        "currency": "SGD", "exchange_rate": 1.34},
    {"id": 11, "name": "Saudi Arabia",          "region": "Region 2 (Middle East/East Asia)", "timezone": "Asia/Riyadh",           "currency": "SAR", "exchange_rate": None},
    {"id": 12, "name": "Qatar",                 "region": "Region 2 (Middle East/East Asia)", "timezone": "Asia/Qatar",            "currency": "QAR", "exchange_rate": None},
    {"id": 13, "name": "Malaysia",              "region": "Region 2 (Middle East/East Asia)", "timezone": "Asia/Kuala_Lumpur",     "currency": "MYR", "exchange_rate": None},
    {"id": 14, "name": "Japan",                 "region": "Region 2 (Middle East/East Asia)", "timezone": "Asia/Tokyo",            "currency": "JPY", "exchange_rate": 149.5},
    {"id": 15, "name": "Sri Lanka",             "region": "Region 3 (South Asia/Africa)",     "timezone": "Asia/Colombo",          "currency": "LKR", "exchange_rate": None},
    {"id": 16, "name": "Bangladesh",            "region": "Region 3 (South Asia/Africa)",     "timezone": "Asia/Dhaka",            "currency": "BDT", "exchange_rate": None},
    {"id": 17, "name": "South Africa",          "region": "Region 3 (South Asia/Africa)",     "timezone": "Africa/Johannesburg",   "currency": "ZAR", "exchange_rate": 18.5},
    {"id": 18, "name": "Kenya",                 "region": "Region 3 (South Asia/Africa)",     "timezone": "Africa/Nairobi",        "currency": "KES", "exchange_rate": None},
    {"id": 19, "name": "Nigeria",               "region": "Region 3 (South Asia/Africa)",     "timezone": "Africa/Lagos",          "currency": "NGN", "exchange_rate": None},
    {"id": 20, "name": "India",                 "region": "Region 4 (India)",                 "timezone": "Asia/Kolkata",          "currency": "INR", "exchange_rate": 83.5},
]

# Base price USD by (course_id, region)
COURSE_PRICING = {
    (1, "Region 1 (Americas/Europe)"):       1495,
    (1, "Region 2 (Middle East/East Asia)"): 1195,
    (1, "Region 3 (South Asia/Africa)"):      995,
    (1, "Region 4 (India)"):                  995,
    (2, "Region 1 (Americas/Europe)"):       1295,
    (2, "Region 2 (Middle East/East Asia)"): 1095,
    (2, "Region 3 (South Asia/Africa)"):      895,
    (2, "Region 4 (India)"):                  895,
    (3, "Region 1 (Americas/Europe)"):       1395,
    (3, "Region 2 (Middle East/East Asia)"): 1095,
    (3, "Region 3 (South Asia/Africa)"):      895,
    (3, "Region 4 (India)"):                  895,
    (4, "Region 1 (Americas/Europe)"):        995,
    (4, "Region 2 (Middle East/East Asia)"):  795,
    (4, "Region 3 (South Asia/Africa)"):      595,
    (4, "Region 4 (India)"):                  595,
    (5, "Region 1 (Americas/Europe)"):       1195,
    (5, "Region 2 (Middle East/East Asia)"):  995,
    (5, "Region 3 (South Asia/Africa)"):      795,
    (5, "Region 4 (India)"):                  795,
    (6, "Region 1 (Americas/Europe)"):       1495,
    (6, "Region 2 (Middle East/East Asia)"): 1195,
    (6, "Region 3 (South Asia/Africa)"):      995,
    (6, "Region 4 (India)"):                  995,
}

PRICING_TIERS = [
    {"id": 1, "name": "Bronze", "percentage": 15},
    {"id": 2, "name": "Silver", "percentage": 30},
    {"id": 3, "name": "Gold",   "percentage": 60},
]

TRAINING_MODES = [
    {"value": "live_virtual",       "label": "Live Virtual"},
    {"value": "live_classroom",     "label": "Live Classroom"},
    {"value": "online_self_paced",  "label": "Online Self-Paced"},
]

STATUSES = ["Draft", "Published", "Archived"]

DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# US week convention: Sun=0, Mon=1, ..., Sat=6
DAY_TO_US_DOW = {"Sun": 0, "Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6}
