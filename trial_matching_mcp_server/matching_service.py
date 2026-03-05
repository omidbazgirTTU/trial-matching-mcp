"""Trial matching orchestration."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .data_loader import list_patients
from .medical_research_client import MCPRemoteError, call_tool


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
