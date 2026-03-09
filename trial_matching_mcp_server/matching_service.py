"""Trial matching orchestration."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pgeocode

from .data_loader import PACKAGE_ROOT, list_patients
from .medical_research_client import MCPRemoteError, call_homecare_tool, call_tool

SITE_DIRECTORY: Dict[str, List[Dict[str, Any]]] = {
    "ALT-TRIAL-001": [
        {
            "facility": "Emory Midtown Diabetes Center",
            "city": "Atlanta, GA",
            "distance_miles": 12,
            "active_centers": [
                {"facility": "Emory Midtown Diabetes Center", "city": "Atlanta, GA"},
                {"facility": "Piedmont Clinical Research", "city": "Atlanta, GA"},
            ],
        },
        {
            "facility": "Northside Endocrine Trials Unit",
            "city": "Sandy Springs, GA",
            "distance_miles": 18,
            "active_centers": [
                {"facility": "Northside Endocrine Trials Unit", "city": "Sandy Springs, GA"}
            ],
        },
    ],
    "ALT-TRIAL-002": [
        {
            "facility": "Piedmont Heart Institute",
            "city": "Atlanta, GA",
            "distance_miles": 10,
            "active_centers": [
                {"facility": "Piedmont Heart Institute", "city": "Atlanta, GA"},
                {"facility": "Wellstar Clinical Research", "city": "Marietta, GA"},
            ],
        },
        {
            "facility": "Augusta Heart Failure Program",
            "city": "Augusta, GA",
            "distance_miles": 148,
            "active_centers": [
                {"facility": "Augusta Heart Failure Program", "city": "Augusta, GA"}
            ],
        },
    ],
    "ALT-TRIAL-003": [
        {
            "facility": "Emory Nephrology Research",
            "city": "Atlanta, GA",
            "distance_miles": 14,
            "active_centers": [
                {"facility": "Emory Nephrology Research", "city": "Atlanta, GA"},
                {"facility": "Atlanta Kidney Institute", "city": "Decatur, GA"},
            ],
        },
        {
            "facility": "UF Health Jacksonville",
            "city": "Jacksonville, FL",
            "distance_miles": 347,
            "active_centers": [
                {"facility": "UF Health Jacksonville", "city": "Jacksonville, FL"}
            ],
        },
    ],
}

DEFAULT_SITE = {
    "facility": "Coordinating Center TBD",
    "city": "Virtual",
    "distance_miles": 0,
    "active_centers": [{"facility": "Pending", "city": "TBD"}],
}

PRIMARY_ENDPOINT_HINTS = {
    "Type 2 Diabetes Mellitus": "Change in HbA1c vs. baseline",
    "Heart Failure with Reduced Ejection Fraction": "NT-proBNP + KCCQ composite",
    "Chronic Kidney Disease w/ Albuminuria": "Percent change in UACR / eGFR slope",
}

FOLLOW_UPS_PATH = PACKAGE_ROOT / "coordinator_followups.json"
HOMECARE_CACHE_PATH = PACKAGE_ROOT / "homecare_patients_cache.json"
NOMINATIM = pgeocode.Nominatim("us")


def patient_cards() -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for patient in list_patients():
        cards.append(
            {
                "patient_id": patient["patient_id"],
                "name": patient["name"],
                "primary_condition": patient["primary_condition"],
                "alternate_need": patient["alternate_need"],
                "current_therapies": patient["current_therapies"],
                "exclude_mechanisms": patient.get("exclude_mechanisms", []),
            }
        )
    return cards


def _get_patient(patient_id: str) -> Dict[str, Any]:
    patient = next((p for p in list_patients() if p["patient_id"] == patient_id), None)
    if not patient:
        raise ValueError(f"patient '{patient_id}' not found")
    return patient


def _fetch_homecare_profile(patient: Dict[str, Any]) -> Dict[str, Any] | None:
    homecare_id = patient.get("homecare_patient_id")
    if not homecare_id:
        return None
    cache = _load_homecare_cache()
    cached = cache.get(homecare_id)
    if cached and (datetime.now(timezone.utc).timestamp() - cached.get("ts", 0) < 3600):
        return _normalize_homecare_profile(cached.get("profile"))
    try:
        profile = call_homecare_tool("patient_profile", {"patient_id": homecare_id})
    except MCPRemoteError:
        return _normalize_homecare_profile(cached.get("profile")) if cached else None
    normalized = _normalize_homecare_profile(profile)
    if normalized is None:
        return normalized
    cache[homecare_id] = {"ts": datetime.now(timezone.utc).timestamp(), "profile": normalized}
    _save_homecare_cache(cache)
    return normalized


def _patient_zip(patient: Dict[str, Any]) -> str | None:
    profile = _fetch_homecare_profile(patient)
    if profile:
        patient_block = profile.get("patient") or profile.get("structuredContent", {}).get("patient")
        if not patient_block and "structuredContent" in profile:
            patient_block = profile["structuredContent"].get("patient")
        if patient_block:
            zip_code = patient_block.get("zip_code")
            if zip_code:
                return str(zip_code).zfill(5)
    fallback = patient.get("fallback_zip")
    if fallback:
        return str(fallback).zfill(5)
    return None


def _zip_distance_miles(zip_a: str | None, zip_b: str | None) -> float | None:
    if not zip_a or not zip_b:
        return None
    info_a = NOMINATIM.query_postal_code(zip_a)
    info_b = NOMINATIM.query_postal_code(zip_b)
    if info_a is None or info_b is None:
        return None
    if info_a.latitude is None or info_b.latitude is None:
        return None
    return float(
        ((info_a.latitude - info_b.latitude) ** 2 + (info_a.longitude - info_b.longitude) ** 2)
        ** 0.5
        * 69.0
    )


def _ensure_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (list, dict)):
        try:
            return json.dumps(payload, indent=2)
        except Exception:
            return str(payload)
    return str(payload)


def _load_followups() -> List[Dict[str, Any]]:
    if FOLLOW_UPS_PATH.exists():
        try:
            return json.loads(FOLLOW_UPS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_followups(entries: List[Dict[str, Any]]) -> None:
    FOLLOW_UPS_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _load_homecare_cache() -> Dict[str, Any]:
    if HOMECARE_CACHE_PATH.exists():
        try:
            return json.loads(HOMECARE_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_homecare_cache(data: Dict[str, Any]) -> None:
    HOMECARE_CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalize_homecare_profile(profile: Any) -> Dict[str, Any] | None:
    if profile is None:
        return None
    if isinstance(profile, dict):
        return profile
    if isinstance(profile, str):
        try:
            return json.loads(profile)
        except Exception:
            return None
    return None


def _build_search_params(patient: Dict[str, Any], limit: int) -> Dict[str, Any]:
    query_terms = [patient.get("alternate_need", ""), patient.get("notes", "")]
    params = {
        "condition": patient.get("primary_condition"),
        "status": "RECRUITING",
        "query": " ".join(filter(None, query_terms)).strip(),
        "page_size": max(5, limit * 2),
    }
    return params


def _fetch_trials(patient: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    params = _build_search_params(patient, limit)
    result_text = call_tool("search_trials", params)
    trials = _parse_trial_text(result_text)
    if not trials:
        fallback = {
            "condition": patient.get("primary_condition"),
            "status": "RECRUITING",
            "page_size": max(5, limit * 2),
        }
        result_text = call_tool("search_trials", fallback)
        trials = _parse_trial_text(result_text)
    enriched: List[Dict[str, Any]] = []
    exclude = [mech.lower() for mech in patient.get("exclude_mechanisms", [])]
    for trial in trials:
        intervention_text = " ".join(trial.get("interventions") or [])
        mechanism = intervention_text.lower()
        if exclude and any(keyword in mechanism for keyword in exclude if keyword):
            continue
        enriched.append(
            {
                "nct_id": trial.get("nct_id"),
                "title": trial.get("title"),
                "status": trial.get("status"),
                "phase": trial.get("phase"),
                "study_type": trial.get("study_type"),
                "conditions": trial.get("conditions"),
                "mechanism": trial.get("interventions"),
                "enrollment": trial.get("enrollment"),
            }
        )
        if len(enriched) >= limit:
            break
    return enriched


def _parse_trial_text(text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not isinstance(text, str):
        return entries
    if "**NCT" in text:
        text = "**NCT" + text.split("**NCT", 1)[1]
    blocks = [blk.strip() for blk in re.split(r"\n\s*---\s*\n", text) if blk.strip()]
    for block in blocks:
        if block.startswith("*More results"):
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        first = lines[0]
        match = re.match(r"\*\*(?P<nct>NCT\w+)\*\*:\s*(?P<title>.+)", first)
        if not match:
            continue
        trial = {
            "nct_id": match.group("nct"),
            "title": match.group("title"),
            "status": None,
            "phase": None,
            "study_type": None,
            "conditions": None,
            "interventions": None,
            "enrollment": None,
        }
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "status":
                trial["status"] = value
            elif key == "phase":
                trial["phase"] = value
            elif key == "study type":
                trial["study_type"] = value
            elif key == "conditions":
                trial["conditions"] = [cond.strip() for cond in value.split(",")]
            elif key == "interventions":
                trial["interventions"] = [cond.strip() for cond in value.split(",")]
            elif key == "enrollment":
                trial["enrollment"] = value
        entries.append(trial)
    return entries


def _score_trial(
    patient: Dict[str, Any], trial: Dict[str, Any], distance_miles: int | float | None
) -> float:
    score = 0.58
    condition = (patient.get("primary_condition") or "").lower()
    title = (trial.get("title") or "").lower()
    phase = (trial.get("phase") or "").lower()
    status = (trial.get("status") or "").lower()

    if condition and condition.split()[0] in title:
        score += 0.12
    mechanism = " ".join(trial.get("mechanism") or []).lower()
    current_mechs = " ".join(patient.get("current_therapies") or []).lower()
    if mechanism and not any(token in mechanism for token in current_mechs.split()):
        score += 0.12
    else:
        score -= 0.05
    if phase in {"phase 2", "phase 3", "phase2/phase3"}:
        score += 0.08
    if status == "recruiting":
        score += 0.04
    if distance_miles is not None:
        if distance_miles <= 25:
            score += 0.08
        elif distance_miles <= 75:
            score += 0.03
        elif distance_miles > 150:
            score -= 0.08
    return max(0.35, min(score, 0.95))


def _alignment_bucket(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.65:
        return "moderate"
    return "watch"


def _lookup_site_info(patient_id: str, trial_index: int) -> Dict[str, Any]:
    patient = _get_patient(patient_id)
    patient_zip = _patient_zip(patient)
    sites = SITE_DIRECTORY.get(patient_id) or [DEFAULT_SITE]
    idx = min(trial_index, len(sites) - 1)
    record = sites[idx]
    distance = record.get("distance_miles")
    if patient_zip:
        site_zip = record.get("zip") or record.get("zip_code")
        computed = _zip_distance_miles(patient_zip, site_zip)
        if computed is not None:
            distance = round(computed, 1)
    return {
        "facility": record["facility"],
        "city": record["city"],
        "distance_miles": distance,
        "active_centers": [
            {"facility": center["facility"], "city": center["city"]}
            for center in record.get("active_centers", [])
        ],
        "patient_zip": patient_zip,
    }


def _endpoint_hint(condition: str | None) -> str:
    if not condition:
        return "Clinical endpoint pending protocol review"
    return PRIMARY_ENDPOINT_HINTS.get(
        condition, "Clinical endpoint pending protocol review"
    )


def match_trials(patient_id: str, limit: int = 5) -> Dict[str, Any]:
    patient = next((p for p in list_patients() if p["patient_id"] == patient_id), None)
    if not patient:
        raise ValueError("patient not found")
    try:
        trials = _fetch_trials(patient, limit)
    except MCPRemoteError as exc:
        raise ValueError(f"Medical research MCP error: {exc}") from exc
    return {
        "patient_id": patient_id,
        "patient": patient,
        "matched_trials": trials,
        "summary": {
            "requested": limit,
            "returned": len(trials),
        },
    }


def trial_detail_brief(nct_id: str) -> Dict[str, Any]:
    if not nct_id:
        raise ValueError("nct_id is required")
    details = call_tool("get_trial", {"nct_id": nct_id})
    eligibility = call_tool("get_trial_eligibility", {"nct_id": nct_id})
    return {
        "nct_id": nct_id.upper(),
        "details_text": _ensure_text(details),
        "eligibility_text": _ensure_text(eligibility),
    }


def eligibility_gap_analysis(patient_id: str, nct_id: str) -> Dict[str, Any]:
    patient = _get_patient(patient_id)
    eligibility_text = _ensure_text(
        call_tool("get_trial_eligibility", {"nct_id": nct_id})
    )
    signals: List[Dict[str, str]] = []
    condition = (patient.get("primary_condition") or "").lower()
    if condition and condition in eligibility_text.lower():
        signals.append({"type": "alignment", "message": "Primary condition mentioned"})
    for therapy in patient.get("current_therapies", []):
        if therapy.lower() in eligibility_text.lower():
            signals.append(
                {
                    "type": "attention",
                    "message": f"Therapy '{therapy}' appears in criteria (possible washout needed)",
                }
            )
    if "age" in eligibility_text.lower():
        signals.append({"type": "info", "message": "Review age window requirements"})

    summary = "eligibility text requires manual review"
    if signals:
        summary = ", ".join(sig["message"] for sig in signals[:3])

    return {
        "patient_id": patient_id,
        "nct_id": nct_id.upper(),
        "eligibility_text": eligibility_text,
        "signals": signals,
        "summary": summary,
    }


def build_recruitment_shortlist(
    patient_ids: List[str] | None = None, trials_per_patient: int = 3
) -> Dict[str, Any]:
    patients = list_patients()
    if patient_ids:
        wanted = {pid.upper() for pid in patient_ids}
        patients = [p for p in patients if p["patient_id"].upper() in wanted]
        if not patients:
            raise ValueError("No patients matched the provided patient_ids.")

    shortlist: List[Dict[str, Any]] = []
    considered: List[Dict[str, Any]] = []

    for patient in patients:
        descriptor = {"patient_id": patient["patient_id"], "name": patient["name"]}
        try:
            trials = _fetch_trials(patient, limit=trials_per_patient)
        except MCPRemoteError as exc:
            descriptor["note"] = f"medical research MCP error: {exc}"
            trials = []
        considered.append(descriptor)

        for idx, trial in enumerate(trials):
            site_info = _lookup_site_info(patient["patient_id"], idx)
            probability = _score_trial(
                patient, trial, site_info.get("distance_miles")
            )
            shortlist.append(
                {
                    "patient_id": patient["patient_id"],
                    "patient_name": patient["name"],
                    "primary_condition": patient["primary_condition"],
                    "nct_id": trial.get("nct_id"),
                    "trial_title": trial.get("title"),
                    "phase": trial.get("phase"),
                    "status": trial.get("status"),
                    "mechanism": trial.get("mechanism"),
                    "probability_of_eligibility": probability,
                    "eligibility_alignment": _alignment_bucket(probability),
                    "primary_endpoint_hint": _endpoint_hint(
                        patient.get("primary_condition")
                    ),
                    "nearest_site": {
                        "facility": site_info["facility"],
                        "city": site_info["city"],
                        "distance_miles": site_info["distance_miles"],
                    },
                    "distance_miles": site_info["distance_miles"],
                    "active_recruiting_centers": site_info["active_centers"],
                    "active_center_count": len(site_info["active_centers"]),
                    "priority_reason": "Mechanism distinct from current therapy mix",
                }
            )

    shortlist.sort(
        key=lambda entry: (-entry["probability_of_eligibility"], entry["distance_miles"])
    )
    for idx, entry in enumerate(shortlist, 1):
        entry["rank"] = idx

    avg_probability = (
        sum(item["probability_of_eligibility"] for item in shortlist) / len(shortlist)
        if shortlist
        else 0.0
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patients_considered": considered,
        "shortlist": shortlist,
        "summary": {
            "patients_considered": len(considered),
            "total_candidates": len(shortlist),
            "avg_probability": round(avg_probability, 3),
        },
    }


def geospatial_coverage_summary(
    patient_ids: List[str] | None = None,
) -> Dict[str, Any]:
    patients = list_patients()
    if patient_ids:
        wanted = {pid.upper() for pid in patient_ids}
        patients = [p for p in patients if p["patient_id"].upper() in wanted]
    radius_buckets = {"<=25": 0, "<=50": 0, "<=100": 0, ">100": 0}
    by_patient: List[Dict[str, Any]] = []
    for patient in patients:
        entries = []
        patient_zip = _patient_zip(patient)
        site_list = SITE_DIRECTORY.get(patient["patient_id"], [])
        for idx, site in enumerate(site_list or [DEFAULT_SITE]):
            record = _lookup_site_info(patient["patient_id"], idx)
            distance = record["distance_miles"] or site.get("distance_miles", 0)
            if distance <= 25:
                radius_buckets["<=25"] += 1
            elif distance <= 50:
                radius_buckets["<=50"] += 1
            elif distance <= 100:
                radius_buckets["<=100"] += 1
            else:
                radius_buckets[">100"] += 1
            entries.append(
                {
                    "facility": record["facility"],
                    "city": record["city"],
                    "distance_miles": distance,
                    "active_centers": record["active_centers"],
                    "patient_zip": patient_zip,
                }
            )
        by_patient.append(
            {
                "patient_id": patient["patient_id"],
                "name": patient["name"],
                "sites": entries,
            }
        )
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "radius_buckets": radius_buckets,
        "patients": by_patient,
    }


def enrollment_signal_snapshot(
    patient_id: str | None = None, condition: str | None = None
) -> Dict[str, Any]:
    if not condition:
        if not patient_id:
            raise ValueError("Provide either patient_id or condition")
        patient = _get_patient(patient_id)
        condition = patient.get("primary_condition")
    condition = condition or "Clinical Trial"

    recruiting = call_tool(
        "count_trials", {"condition": condition, "status": "RECRUITING"}
    )
    completed = call_tool(
        "count_trials", {"condition": condition, "status": "COMPLETED"}
    )
    sample = call_tool(
        "search_trials",
        {"condition": condition, "status": "RECRUITING", "page_size": 3},
    )

    return {
        "condition": condition,
        "patients_tracked": [patient_id] if patient_id else [],
        "counts": {
            "recruiting": _ensure_text(recruiting),
            "completed": _ensure_text(completed),
        },
        "sample_trials": _ensure_text(sample),
    }


def record_follow_up(
    patient_id: str, note: str, owner: str = "coordinator", due_date: str | None = None
) -> Dict[str, Any]:
    _get_patient(patient_id)  # validate
    entries = _load_followups()
    entry = {
        "patient_id": patient_id,
        "note": note,
        "owner": owner,
        "due_date": due_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }
    entries.append(entry)
    _save_followups(entries)
    return entry


def list_follow_ups(patient_id: str | None = None) -> Dict[str, Any]:
    entries = _load_followups()
    if patient_id:
        entries = [e for e in entries if e.get("patient_id") == patient_id]
    return {"count": len(entries), "items": entries}
