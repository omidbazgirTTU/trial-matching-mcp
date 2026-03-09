"""Register MCP UI widgets (HTML) for trial matching visualizations."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

MIME_TYPE = "text/html;profile=mcp-app"
WIDGETS_DIR = Path(__file__).resolve().parent.parent / "widgets"

WIDGET_URIS = {
    "patient_queue": "ui://trial-matching/patient-queue.html",
    "trial_matches": "ui://trial-matching/trial-matches.html",
    "program_summary": "ui://trial-matching/program-summary.html",
    "recruitment_shortlist": "ui://trial-matching/recruitment-shortlist.html",
    "trial_detail": "ui://trial-matching/trial-detail.html",
    "eligibility_gaps": "ui://trial-matching/eligibility-gaps.html",
    "geo_coverage": "ui://trial-matching/geospatial-coverage.html",
    "enrollment_signals": "ui://trial-matching/enrollment-signals.html",
    "follow_up_log": "ui://trial-matching/follow-up-log.html",
}


def register_widgets(mcp: FastMCP) -> None:
    for name, uri in WIDGET_URIS.items():
        html_file = WIDGETS_DIR / f"{name}.html"
        _register_widget(mcp, name, uri, html_file)


def _register_widget(mcp: FastMCP, name: str, uri: str, path: Path) -> None:
    if not path.exists():
        return

    @mcp.resource(
        uri,
        name=name.replace("_", " ").title(),
        description=f"UI widget for {name.replace('_', ' ')}",
        mime_type=MIME_TYPE,
    )
    def _read_widget() -> str:
        return path.read_text(encoding="utf-8")
