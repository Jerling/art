"""WeChat Message Service with MCP tool execution integration.

This service processes WeChat messages and optionally triggers MCP tool calls
via the OpenViking MCP Server (ADR-001: tool execution layer).

The message flow is:
  1. WeChat message received via webhook
  2. Message parsed and validated
  3. AI Brain (GLM) determines intent
  4. If tool execution is needed, MCP Client calls OpenViking tools
  5. Tool result returned to user via WeChat

References:
  - Technical Plan ADR-001: OpenViking MCP定位
  - SPRINT-PLAN.md: Sprint 2 scope
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.worker.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPToolExecutionError,
    ToolCallResult,
    ToolInfo,
    get_mcp_client,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class WeChatMessageContext:
    """Context for a WeChat message being processed."""

    openid: str
    content: str
    msg_type: str | None = None
    raw_data: dict[str, Any] | None = None


@dataclass
class ToolExecutionResult:
    """Result of executing an MCP tool in response to a WeChat message."""

    success: bool
    tool_name: str
    result: ToolCallResult | None
    error: str | None = None
    latency_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class WeChatMessageService:
    """Service for processing WeChat messages with MCP tool integration.

    This service implements the integration layer between WeChat messages
    and the MCP tool execution layer per ADR-001.

    The service does NOT handle:
    - Message signature verification (handled by WeChatCrypto in integrations/)
    - Message persistence (handled by storage layer)
    - AI intent parsing (handled by AI Brain / LLM layer)

    Usage:
        service = WeChatMessageService(mcp_client)
        result = await service.handle_message(context)
        if result.success:
            await service.send_response(result)
    """

    def __init__(self, mcp_client: MCPClient | None = None) -> None:
        """Initialize the WeChat message service.

        Args:
            mcp_client: Optional MCP client instance. If not provided,
                       a client will be created from the global config.
        """
        self._mcp_client = mcp_client
        self._available_tools: list[ToolInfo] | None = None

    # ── MCP Client management ───────────────────────────────────────────────

    @property
    def mcp_client(self) -> MCPClient:
        """Get or create the MCP client.

        Returns:
            MCPClient instance.
        """
        if self._mcp_client is None:
            self._mcp_client = get_mcp_client()
        return self._mcp_client

    async def ensure_connected(self) -> bool:
        """Ensure MCP client is connected.

        Returns:
            True if connected, False if connection failed.
        """
        if self.mcp_client.is_connected:
            return True
        try:
            await self.mcp_client.connect()
            return True
        except MCPConnectionError as e:
            logger.error("Failed to connect to OpenViking MCP: %s", e)
            return False

    async def disconnect(self) -> None:
        """Disconnect the MCP client if connected."""
        if self._mcp_client is not None and self._mcp_client.is_connected:
            await self._mcp_client.disconnect()

    # ── Tool operations ─────────────────────────────────────────────────────

    async def list_available_tools(self) -> list[ToolInfo]:
        """List all tools available from the OpenViking MCP server.

        Results are cached until disconnect.

        Returns:
            List of ToolInfo objects.

        Raises:
            MCPConnectionError: If not connected to the server.
        """
        if self._available_tools is None:
            self._available_tools = await self.mcp_client.list_tools()
        return self._available_tools

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        """Execute an MCP tool in response to a WeChat message.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Optional arguments for the tool.

        Returns:
            ToolExecutionResult with success status and result/error.
        """
        if not await self.ensure_connected():
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                result=None,
                error="Failed to connect to OpenViking MCP server",
            )

        try:
            result = await self.mcp_client.call_tool(tool_name, arguments)
            return ToolExecutionResult(
                success=not result.is_error,
                tool_name=tool_name,
                result=result,
                latency_ms=result.latency_ms,
            )
        except MCPConnectionError as e:
            logger.error("MCP connection error during tool execution: %s", e)
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                result=None,
                error=f"MCP connection error: {e}",
            )
        except MCPToolExecutionError as e:
            logger.error("MCP tool execution error: %s", e)
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                result=None,
                error=f"Tool execution failed: {e}",
            )

    # ── Message handling ─────────────────────────────────────────────────────

    async def handle_message(
        self,
        context: WeChatMessageContext,
    ) -> ToolExecutionResult | None:
        """Process a WeChat message and potentially execute MCP tools.

        This method determines if the message requires MCP tool execution
        and executes the appropriate tool.

        The decision logic is:
        1. If message contains a known tool trigger pattern, execute that tool
        2. Otherwise, return None (no tool execution needed)

        Args:
            context: The WeChat message context.

        Returns:
            ToolExecutionResult if a tool was executed, None otherwise.
        """
        # Check if message matches any tool trigger patterns
        tool_name, arguments = self._parse_message_for_tool(context)
        if tool_name is None:
            return None

        logger.info(
            "WeChat message triggered tool execution: openid=%s tool=%s",
            context.openid,
            tool_name,
        )

        return await self.execute_tool(tool_name, arguments)

    def _parse_message_for_tool(
        self,
        context: WeChatMessageContext,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Parse a WeChat message to determine if a tool should be triggered.

        This is a simple pattern-matching implementation. In production,
        this would be replaced by AI intent parsing via the LLM layer.

        Args:
            context: The WeChat message context.

        Returns:
            Tuple of (tool_name, arguments) or (None, None) if no tool triggered.
        """
        content = context.content.strip().lower()

        # Simple trigger patterns for testing
        # In production, this would use AI intent parsing
        if content.startswith("/tools"):
            # List available tools
            return "list_tools", None

        if content.startswith("/search "):
            # Search tool
            query = content[8:].strip()
            return "search", {"query": query}

        if content.startswith("/execute "):
            # Generic tool execution
            parts = content[9:].split(maxsplit=1)
            if len(parts) >= 1:
                tool_name = parts[0]
                args = {}
                if len(parts) >= 2:
                    args["input"] = parts[1]
                return tool_name, args

        # No tool triggered
        return None, None

    # ── Response formatting ─────────────────────────────────────────────────

    def format_tool_result_for_wechat(
        self,
        result: ToolExecutionResult,
    ) -> str:
        """Format a tool execution result for WeChat message response.

        Args:
            result: The tool execution result.

        Returns:
            Formatted string suitable for WeChat message response.
        """
        if not result.success:
            return f"Tool execution failed: {result.error}"

        if result.result is None:
            return "Tool executed but returned no result"

        # Extract text content from the result
        texts = result.result.text_content
        if not texts:
            return "Tool executed successfully"

        # Format the response
        response_lines = []
        if result.result.is_error:
            response_lines.append("[Error]")
        for text in texts:
            response_lines.append(text)

        if result.latency_ms > 0:
            response_lines.append(f"\n(Latency: {result.latency_ms:.0f}ms)")

        return "\n".join(response_lines)
