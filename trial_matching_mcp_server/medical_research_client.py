"""Async client wrapper around the Medical Research MCP server."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastmcp.client import Client

MCP_URL = "https://gx3ncbwwsa6c5mkjqk45tafesa.apigateway.us-ashburn-1.oci.customer-oci.com/v1/medical-research-mcp"


class MCPRemoteError(RuntimeError):
    """Raised when the remote MCP returns an error."""


def _call_async(tool_name: str, arguments: Dict[str, Any]) -> Any:
    async def runner() -> Any:
        client = Client(MCP_URL, name="trial-matching-mcp")
        async with client:
            response = await client.call_tool(tool_name, arguments)
            if response.is_error:
                raise MCPRemoteError(response.error_message or "Unknown MCP error")
            data = response.data
            if hasattr(data, "result"):
                return data.result
            # Fallback to structured or content payloads
            if response.structured_content and "result" in response.structured_content:
                return response.structured_content["result"]
            if response.content:
                return response.content[0].text if response.content else ""
            return data

    return asyncio.run(runner())


def call_tool(name: str, args: Dict[str, Any]) -> Any:
    return _call_async(name, args)
