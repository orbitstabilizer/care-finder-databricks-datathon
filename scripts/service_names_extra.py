"""Readable names and dropdown groups for the 11 service labels added with prompt pa_single_v2.

app/config.py SERVICE_GROUPS is the single source for the original 49 labels. The 11 labels
below are not in it yet (the app is being redesigned separately). scripts/build_facility_service.py
merges NEW_SERVICES into the names it reads from app/config.py; app/config.py wins if it
already has a label. When the app step adds these to SERVICE_GROUPS, this file can stay as is.

NEW_SERVICES: label -> (group, readable name). Groups reuse the app's existing group names,
except ayush_traditional_medicine, which gets its own group so it never mixes into
emergency-style results.
"""

NEW_SERVICES = {
    "urology": ("Other specialties", "Urology and kidney stone treatment"),
    "diabetes_endocrinology": ("Other specialties", "Diabetes, thyroid and hormone care"),
    "health_checkup_vaccination": ("Other specialties", "Health check-ups and vaccination"),
    "cardiac_diagnostics": ("Imaging and diagnostics", "Heart tests and non-invasive cardiology"),
    "neurology": ("Other specialties", "Neurology (non-surgical brain and nerve care)"),
    "ayush_traditional_medicine": ("Traditional medicine (AYUSH)",
                                   "Ayurveda, homeopathy and other traditional medicine"),
    "gynecology": ("Maternity and newborn", "Gynaecology (non-pregnancy women's health)"),
    "proctology": ("Surgery", "Piles, fistula and fissure treatment"),
    "pain_management": ("Other specialties", "Pain management"),
    "vascular_surgery": ("Surgery", "Vascular surgery and varicose veins"),
    "cardiology_medical": ("Other specialties", "Cardiology (heart care, no surgery)"),
}

NEW_SERVICE_NAME = {k: v[1] for k, v in NEW_SERVICES.items()}
NEW_SERVICE_GROUP = {k: v[0] for k, v in NEW_SERVICES.items()}
