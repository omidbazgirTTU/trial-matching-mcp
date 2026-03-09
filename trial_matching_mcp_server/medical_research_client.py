"""Async client wrapper around the Medical Research MCP server."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastmcp.client import Client

MCP_URL = "https://gx3ncbwwsa6c5mkjqk45tafesa.apigateway.us-ashburn-1.oci.customer-oci.com/v1/medical-research-mcp"
HOMECARE_URL = "https://homecare-cohort-mcp.vercel.app/mcp/"


class MCPRemoteError(RuntimeError):
    """Raised when the remote MCP returns an error."""


def _call_async(tool_name: str, arguments: Dict[str, Any], backend: str) -> Any:
    async def runner() -> Any:
        client = Client(backend, name="trial-matching-mcp")
        async with client:
            response = await client.call_tool(tool_name, arguments)
            if response.is_error:
                raise MCPRemoteError(response.error_message or "Unknown MCP error")
            if response.structured_content:
                return response.structured_content
            data = response.data
            if hasattr(data, "result"):
                return data.result
            if response.content:
                return response.content[0].text if response.content else ""
            return data

    return asyncio.run(runner())


def call_tool(name: str, args: Dict[str, Any]) -> Any:
    return _call_async(name, args, MCP_URL)


def call_homecare_tool(name: str, args: Dict[str, Any]) -> Any:
    return _call_async(name, args, HOMECARE_URL)
