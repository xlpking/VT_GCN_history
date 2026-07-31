"""Build comprehensive manual_overrides from LLM review of 21 no-magnitude records."""
import json
from datetime import datetime, timezone

# Load existing overrides
with open("data/manual_overrides.json", "r") as f:
    overrides = json.load(f)

now = datetime.now(timezone.utc).isoformat()

# GCN43945: clarification, ~22.5 AB mag at 10.25 min, both VT_B and VT_R
overrides["43945"] = {
    "report_type": "upper_limit",
    "bands": ["VT_B", "VT_R"],
    "magnitudes": [
        {"band": "VT_B", "value": 22.5, "unit": "mag", "is_limit": True, "t_mid_hr": 0.171},
        {"band": "VT_R", "value": 22.5, "unit": "mag", "is_limit": True, "t_mid_hr": 0.171},
    ],
    "note": "LLM: ~22.5 AB mag at mid time of 10.25 minutes, non-detection, dark burst",
    "updated_at": now,
}

# GCN43834: upper_limit, 22.0 mag in VT_R, ~47.68 min
overrides["43834"] = {
    "report_type": "upper_limit",
    "bands": ["VT_R"],
    "magnitudes": [
        {"band": "VT_R", "value": 22.0, "unit": "mag", "is_limit": True, "t_mid_hr": 0.795},
    ],
    "note": "LLM: 22.0 mag in VT_R, ~47.68 min post trigger, non-detection",
    "updated_at": now,
}

# GCN39931: upper_limit, VT_R 23.1 mag at 4.0 hours
overrides["39931"] = {
    "report_type": "upper_limit",
    "bands": ["VT_R"],
    "magnitudes": [
        {"band": "VT_R", "value": 23.1, "unit": "mag", "is_limit": True, "t_mid_hr": 4.0},
    ],
    "note": "LLM: 3 sigma limit VT_R 23.1 mag at mid time of 4.0 hours",
    "updated_at": now,
}

# GCN39957: upper_limit (Swift trigger), two epochs: VT_R 21.7@3.2h, VT_R 23.0@6.8h
overrides["39957"] = {
    "report_type": "upper_limit",
    "trigger_source": "Swift",
    "bands": ["VT_R"],
    "magnitudes": [
        {"band": "VT_R", "value": 21.7, "unit": "mag", "is_limit": True, "t_mid_hr": 3.2},
        {"band": "VT_R", "value": 23.0, "unit": "mag", "is_limit": True, "t_mid_hr": 6.8},
    ],
    "note": "LLM: two ToO epochs, VT_R 3sigma 21.7@3.2h and 23.0@6.8h",
    "updated_at": now,
}

# GCN38568: detection, VT_R 23.70+/-0.30 at ~38.55 hours, VT_B limit 23.80
overrides["38568"] = {
    "report_type": "detection",
    "bands": ["VT_R", "VT_B"],
    "magnitudes": [
        {"band": "VT_R", "value": 23.70, "unit": "mag", "is_limit": False, "t_mid_hr": 38.55},
        {"band": "VT_B", "value": 23.80, "unit": "mag", "is_limit": True, "t_mid_hr": 38.55},
    ],
    "note": "LLM: VT_R 23.70+/-0.30 at ~38.55h post trigger, continuous fading; VT_B limit 23.80",
    "updated_at": now,
}

# GCN40444: EP detection, VT_R 21.5+/-0.2 at 1.6 hours
overrides["40444"] = {
    "report_type": "detection",
    "trigger_source": "EP",
    "bands": ["VT_R"],
    "magnitudes": [
        {"band": "VT_R", "value": 21.5, "unit": "mag", "is_limit": False, "t_mid_hr": 1.6},
    ],
    "note": "LLM: EP250512a, VT_R 21.5+/-0.2 at 1.6h after burst",
    "updated_at": now,
}

# GCN37728: upper_limit (Swift trigger), VT_B 24.0, VT_R 23.8 @ ~5.38h
overrides["37728"] = {
    "report_type": "upper_limit",
    "trigger_source": "Swift",
    "bands": ["VT_B", "VT_R"],
    "magnitudes": [
        {"band": "VT_B", "value": 24.0, "unit": "mag", "is_limit": True, "t_mid_hr": 5.38},
        {"band": "VT_R", "value": 23.8, "unit": "mag", "is_limit": True, "t_mid_hr": 5.38},
    ],
    "note": "LLM: 3sigma VT_B 24.0, VT_R 23.8 at ~5.38h, ToO of Swift/BAT GRB",
    "updated_at": now,
}

# GCN37243: upper_limit (SVOM/ECLAIRs), VT 23.0 in both @ ~17h
overrides["37243"] = {
    "report_type": "upper_limit",
    "bands": ["VT_B", "VT_R"],
    "magnitudes": [
        {"band": "VT_B", "value": 23.0, "unit": "mag", "is_limit": True, "t_mid_hr": 17.0},
        {"band": "VT_R", "value": 23.0, "unit": "mag", "is_limit": True, "t_mid_hr": 17.0},
    ],
    "note": "LLM: limit 23.0 mag both channels at ~17h, ToO of EP/Swift GRB",
    "updated_at": now,
}

# GCN37452: duplicate of GCN37453, skip - no data
# GCN38093: clarification - candidate is detector defect, not real
# GCN37826: detection but only qualitative ("5 mag fading"), no specific magnitude value

# GCN39159: detection, VT_B data: 20.91@8.75min, 21.18@12.5min
# Format: mag(AB) VT_B | mag err | mid-observing time since trigger (minutes)
overrides["39159"] = {
    "report_type": "detection",
    "bands": ["VT_B"],
    "magnitudes": [
        {"band": "VT_B", "value": 20.91, "unit": "mag", "is_limit": False, "t_mid_hr": 0.146},
        {"band": "VT_B", "value": 21.18, "unit": "mag", "is_limit": False, "t_mid_hr": 0.208},
    ],
    "note": "LLM: VT_B 20.91 at 8.75min, 21.18 at 12.5min post trigger",
    "updated_at": now,
}

# GCN40960: EP detection, ~20.4 mag in both VT_B and VT_R
overrides["40960"] = {
    "report_type": "detection",
    "trigger_source": "EP",
    "bands": ["VT_B", "VT_R"],
    "magnitudes": [
        {"band": "VT_B", "value": 20.4, "unit": "mag", "is_limit": False, "t_mid_hr": None},
        {"band": "VT_R", "value": 20.4, "unit": "mag", "is_limit": False, "t_mid_hr": None},
    ],
    "note": "LLM: ~20.4 mag in both bands, blue optical source (EP250704a)",
    "updated_at": now,
}

# GCN37820: upper_limit, 3sigma VT_B 23.9, VT_R 23.6 @ ~14.0h
overrides["37820"] = {
    "report_type": "upper_limit",
    "bands": ["VT_B", "VT_R"],
    "magnitudes": [
        {"band": "VT_B", "value": 23.9, "unit": "mag", "is_limit": True, "t_mid_hr": 14.0},
        {"band": "VT_R", "value": 23.6, "unit": "mag", "is_limit": True, "t_mid_hr": 14.0},
    ],
    "note": "LLM: 3sigma VT_B 23.9, VT_R 23.6 at ~14.0h, ToO of SVOM/ECLAIRs GRB",
    "updated_at": now,
}

# Save
with open("data/manual_overrides.json", "w") as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)

print(f"Updated {len(overrides)} overrides total")
print(f"Added magnitude overrides for 8 records")
