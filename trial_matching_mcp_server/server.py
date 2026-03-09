"""FastMCP server for trial matching agent."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from fastmcp import FastMCP

from .data_loader import load_dataset
from .matching_service import (
    build_recruitment_shortlist,
    eligibility_gap_analysis,
    enrollment_signal_snapshot,
    geospatial_coverage_summary,
    list_follow_ups,
    match_trials,
    patient_cards,
    record_follow_up,
    trial_detail_brief,
)
from .ui import WIDGET_URIS, register_widgets

server = FastMCP("trial-matching-mcp-server")
register_widgets(server)


@server.tool(description="List patients flagged for alternate therapy trial matching.")
def list_trial_patients() -> dict[str, Any]:
    cards = patient_cards()
    return {
        "patients": cards,
        "ui": {
            "widgetUri": WIDGET_URIS.get("patient_queue"),
            "data": {"patients": cards},
        },
    }


@server.tool(description="Match live recruiting trials for a patient using the medical research MCP.")
def match_patient_trials(patient_id: str, limit: int = 5) -> dict[str, Any]:
    result = match_trials(patient_id, limit=limit)
    result["ui"] = {
        "widgetUri": WIDGET_URIS.get("trial_matches"),
        "data": {"trials": result.get("matched_trials", [])},
    }
    return result


@server.tool(description="Dataset overview and persona context.")
def trial_matching_summary() -> dict[str, Any]:
    ds = load_dataset()
    payload = {
        "persona": ds.get("persona"),
        "as_of": ds.get("as_of"),
        "patient_count": len(ds.get("patients", [])),
    }
    payload["ui"] = {
        "widgetUri": WIDGET_URIS.get("program_summary"),
        "data": {
            "persona": payload["persona"],
            "as_of": payload["as_of"],
            "patient_count": payload["patient_count"],
        },
    }
    return payload


@server.tool(
    description=(
        "Generate a ranked clinical-trial recruitment shortlist with eligibility scores "
        "and nearest recruiting sites."
    )
)
def generate_recruitment_shortlist(
    patient_ids: list[str] | None = None, trials_per_patient: int = 3
) -> dict[str, Any]:
    shortlist = build_recruitment_shortlist(
        patient_ids=patient_ids, trials_per_patient=trials_per_patient
    )
    shortlist["ui"] = {
        "widgetUri": WIDGET_URIS.get("recruitment_shortlist"),
        "data": {
            "shortlist": shortlist.get("shortlist", []),
            "summary": shortlist.get("summary", {}),
        },
    }
    return shortlist


@server.tool(description="Get a summarized trial brief and eligibility text by NCT ID.")
def get_trial_brief(nct_id: str) -> dict[str, Any]:
    result = trial_detail_brief(nct_id)
    widget_data = {
        "nct_id": result.get("nct_id"),
        "details_text": result.get("details_text"),
        "eligibility_text": result.get("eligibility_text"),
    }
    result["ui"] = {"widgetUri": WIDGET_URIS.get("trial_detail"), "data": widget_data}
    return result


@server.tool(
    description="Compare a patient's profile with trial eligibility text and surface potential gaps."
)
def analyze_trial_eligibility(patient_id: str, nct_id: str) -> dict[str, Any]:
    result = eligibility_gap_analysis(patient_id, nct_id)
    widget_data = {
        "patient_id": result.get("patient_id"),
        "nct_id": result.get("nct_id"),
        "summary": result.get("summary"),
        "signals": result.get("signals"),
    }
    result["ui"] = {"widgetUri": WIDGET_URIS.get("eligibility_gaps"), "data": widget_data}
    return result


@server.tool(description="Summarize nearest trial sites and coverage radius by patient.")
def geospatial_coverage(patient_ids: list[str] | None = None) -> dict[str, Any]:
    result = geospatial_coverage_summary(patient_ids=patient_ids)
    widget_data = {
        "radius_buckets": result.get("radius_buckets"),
        "patients": result.get("patients"),
    }
    result["ui"] = {"widgetUri": WIDGET_URIS.get("geo_coverage"), "data": widget_data}
    return result


@server.tool(description="View recent enrollment activity signals for a condition or patient.")
def enrollment_signals(
    condition: str | None = None, patient_id: str | None = None
) -> dict[str, Any]:
    result = enrollment_signal_snapshot(patient_id=patient_id, condition=condition)
    widget_data = {
        "condition": result.get("condition"),
        "counts": result.get("counts"),
        "sample_trials": result.get("sample_trials"),
    }
    result["ui"] = {
        "widgetUri": WIDGET_URIS.get("enrollment_signals"),
        "data": widget_data,
    }
    return result


@server.tool(description="Record an actionable follow-up item for a patient.")
def log_follow_up(
    patient_id: str,
    note: str,
    owner: str = "coordinator",
    due_date: str | None = None,
) -> dict[str, Any]:
    entry = record_follow_up(patient_id, note, owner=owner, due_date=due_date)
    widget_data = {"items": [entry]}
    entry["ui"] = {"widgetUri": WIDGET_URIS.get("follow_up_log"), "data": widget_data}
    return entry


@server.tool(description="List recorded follow-up items, optionally filtered by patient.")
def list_follow_up_items(patient_id: str | None = None) -> dict[str, Any]:
    result = list_follow_ups(patient_id=patient_id)
    widget_data = {"items": result.get("items", [])}
    result["ui"] = {"widgetUri": WIDGET_URIS.get("follow_up_log"), "data": widget_data}
    return result


def run_http(host: str, port: int) -> None:
    server.run(transport="http", host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the trial matching MCP server.")
    parser.add_argument("--transport", default="http", help="Transport (http or stdio)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.transport == "http":
        run_http(args.host, args.port)
    else:
        server.run(transport=args.transport)


def get_asgi_app():
    app = server.http_app()

    async def wrapped(scope, receive, send):
        if scope.get("type") in {"http", "websocket"}:
            path = scope.get("path", "")
            if path.startswith("/api/mcp.py"):
                new_scope = dict(scope)
                suffix = path[len("/api/mcp.py") :]
                new_scope["path"] = "/mcp" + suffix
                new_scope.setdefault("root_path", "")
                scope = new_scope
            elif path.startswith("/api/mcp"):
                new_scope = dict(scope)
                suffix = path[len("/api/mcp") :]
                new_scope["path"] = "/mcp" + suffix
                new_scope.setdefault("root_path", "")
                scope = new_scope
        await app(scope, receive, send)

    return wrapped


if __name__ == "__main__":
    main()
