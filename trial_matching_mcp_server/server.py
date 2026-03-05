"""FastMCP server for trial matching agent."""

from __future__ import annotations

import argparse
import logging
from typing import Any

from fastmcp import FastMCP

from .data_loader import load_dataset
from .matching_service import match_trials, patient_cards
from .ui import WIDGET_URIS, register_widgets

server = FastMCP("trial-matching-mcp-server")
server.register_extension("io.modelcontextprotocol/ui")
register_widgets(server)


@server.tool(description="List patients flagged for alternate therapy trial matching.")
def list_trial_patients() -> list[dict[str, Any]]:
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
    return {
        "persona": ds.get("persona"),
        "as_of": ds.get("as_of"),
        "patient_count": len(ds.get("patients", [])),
    }


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
