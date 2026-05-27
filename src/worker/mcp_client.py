"""MCP Client for OpenViking tool execution.

ADR-001: OpenViking MCP Server = tool execution layer, separated from
MiniMax inference layer. This client communicates with OpenViking via stdio
using the MCP (Model Context Protocol) JSON-RPC protocol.

References:
  - Technical Plan ADR-001: OpenViking MCP定位
  - MCP Protocol: https://modelcontextprotocol.io
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp import types
from mcp.client.stdio import StdioServerParameters, stdio_client

if TYPE_CHECKING:
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class OpenVikingConfig:
    """OpenViking MCP Server configuration."""

    # Path to the OpenViking MCP server executable
    # If not set, the server is assumed to be unavailable
    command: str | None = None
    # Arguments to pass to the OpenViking command
    args: list[str] = field(default_factory=list)
    # Environment variables for the server process
    env: dict[str, str] | None = None
    # Working directory for the server process
    cwd: str | None = None
    # Connection timeout in seconds
    timeout_seconds: float = 10.0

    @property
    def is_configured(self) -> bool:
        """Return True if OpenViking command is configured."""
        return bool(self.command)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ToolInfo:
    """Normalized tool information from MCP list_tools."""

    name: str
    description: str | None
    input_schema: dict[str, Any]

    @classmethod
    def from_mcp_tool(cls, tool: types.Tool) -> ToolInfo:
        """Convert MCP Tool type to ToolInfo."""
        return cls(
            name=tool.name,
            description=tool.description,
            input_schema=tool.inputSchema,
        )


@dataclass
class ToolCallResult:
    """Result from a tool call."""

    content: list[Any]
    is_error: bool
    latency_ms: float

    @property
    def text_content(self) -> list[str]:
        """Extract text content from the result."""
        texts = []
        for item in self.content:
            if hasattr(item, "text"):
                texts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
        return texts

    @property
    def first_text(self) -> str | None:
        """Return the first text content or None."""
        texts = self.text_content
        return texts[0] if texts else None


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class MCPClientError(Exception):
    """Base exception for MCP client errors."""

    pass


class MCPConnectionError(MCPClientError):
    """Raised when connection to MCP server fails."""

    pass


class MCPToolNotFoundError(MCPClientError):
    """Raised when the requested tool is not found."""

    pass


class MCPToolExecutionError(MCPClientError):
    """Raised when tool execution fails."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# MCP Client
# ─────────────────────────────────────────────────────────────────────────────


class MCPClient:
    """MCP Client for communicating with OpenViking via stdio.

    This client implements the tool execution layer per ADR-001:
    - Receives tool execution requests from the service layer
    - Communicates with OpenViking MCP Server via stdio JSON-RPC
    - Returns structured results to the calling service

    The client is async and designed to be used as a context manager:

        async with MCPClient(config) as client:
            tools = await client.list_tools()
            result = await client.call_tool("search", {"query": "hello"})

    The underlying stdio transport is kept alive for the duration of the
    context manager, allowing multiple tool calls with minimal overhead.

    Latency target: < 300ms per tool call (local, excluding first connect).
    """

    def __init__(self, config: OpenVikingConfig) -> None:
        """Initialize MCP client with OpenViking configuration.

        Args:
            config: OpenViking MCP server configuration.
        """
        self._config = config
        self._server_params: StdioServerParameters | None = None
        self._session: ClientSession | None = None
        self._stdio_transport: tuple[Any, Any] | None = None
        self._connected: bool = False
        self._tool_names_cache: set[str] | None = None

    # ── Context manager lifecycle ─────────────────────────────────────────────

    async def __aenter__(self) -> MCPClient:
        """Connect to OpenViking MCP server on context entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Disconnect from OpenViking MCP server on context exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish connection to OpenViking MCP server via stdio.

        Raises:
            MCPConnectionError: If connection fails or server is not configured.
        """
        if not self._config.is_configured:
            raise MCPConnectionError(
                "OpenViking MCP server not configured. "
                "Set 'openviking.command' in config.json."
            )

        # Build server parameters - command is guaranteed non-None here
        # because is_configured check passed above
        self._server_params = StdioServerParameters(
            command=self._config.command,
            args=self._config.args,
            env=self._config.env,
            cwd=self._config.cwd,
        )

        logger.info(
            "Connecting to OpenViking MCP server: %s %s",
            self._config.command,
            self._config.args,
        )

        try:
            # Establish stdio transport
            stdio_transport = await self._create_stdio_transport(self._server_params)
            self._stdio_transport = stdio_transport
            read_stream, write_stream = stdio_transport

            # Import here to avoid type checking issues at module level
            from mcp.client.session import ClientSession

            # Create and initialize session
            self._session = ClientSession(
                read_stream=read_stream,
                write_stream=write_stream,
            )
            await self._session.initialize()
            self._connected = True
            logger.info("OpenViking MCP server connected successfully")
        except Exception as e:
            self._connected = False
            # Clean up transport on failure
            if self._stdio_transport is not None:
                await self._cleanup_stdio_transport(self._stdio_transport)
                self._stdio_transport = None
            raise MCPConnectionError(f"Failed to connect to OpenViking: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from OpenViking MCP server and clean up resources."""
        # Exit the session first
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing MCP session: %s", e)
            self._session = None

        # Clean up stdio transport
        if self._stdio_transport is not None:
            await self._cleanup_stdio_transport(self._stdio_transport)
            self._stdio_transport = None

        self._connected = False
        logger.info("OpenViking MCP server disconnected")

    async def _create_stdio_transport(
        self, params: StdioServerParameters
    ) -> tuple[Any, Any]:
        """Create stdio transport by entering the stdio_client context.

        This is extracted into a separate method to allow mocking in tests.
        """
        # stdio_client is an async context manager that yields (read_stream, write_stream)
        return await stdio_client(params).__aenter__()

    async def _cleanup_stdio_transport(self, transport: tuple[Any, Any]) -> None:
        """Clean up stdio transport resources."""
        read_stream, write_stream = transport
        try:
            await read_stream.aclose()
        except Exception:
            pass
        try:
            await write_stream.aclose()
        except Exception:
            pass

    # ── Tool operations ───────────────────────────────────────────────────────

    async def list_tools(self) -> list[ToolInfo]:
        """List all tools available from the OpenViking MCP server.

        Returns:
            List of ToolInfo objects describing available tools.

        Raises:
            MCPConnectionError: If not connected to the server.
        """
        self._ensure_connected()

        start = time.perf_counter()
        result = await self._session.list_tools()  # type: ignore[union-attr]
        latency_ms = (time.perf_counter() - start) * 1000

        tools = [ToolInfo.from_mcp_tool(t) for t in result.tools]

        # Cache tool names for O(1) lookups in call_tool
        self._tool_names_cache = {t.name for t in tools}

        logger.debug(
            "list_tools completed in %.2fms, found %d tools",
            latency_ms,
            len(tools),
        )

        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        """Execute a tool on the OpenViking MCP server.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Optional arguments to pass to the tool.

        Returns:
            ToolCallResult with content and latency information.

        Raises:
            MCPConnectionError: If not connected to the server.
            MCPToolNotFoundError: If the tool does not exist.
            MCPToolExecutionError: If tool execution fails.
        """
        self._ensure_connected()

        # First verify the tool exists — use cache if available, else fetch
        if self._tool_names_cache is not None:
            if tool_name not in self._tool_names_cache:
                raise MCPToolNotFoundError(
                    f"Tool '{tool_name}' not found. Cached tools: {self._tool_names_cache}"
                )
        else:
            # First call — populate cache
            tools = await self.list_tools()
            if tool_name not in self._tool_names_cache:  # type: ignore[union-attr]
                raise MCPToolNotFoundError(
                    f"Tool '{tool_name}' not found. Available tools: {self._tool_names_cache}"
                )

        start = time.perf_counter()
        try:
            result = await self._session.call_tool(  # type: ignore[union-attr]
                name=tool_name,
                arguments=arguments or {},
            )
        except Exception as e:
            raise MCPToolExecutionError(
                f"Tool '{tool_name}' execution failed: {e}"
            ) from e

        latency_ms = (time.perf_counter() - start) * 1000

        # Log latency for monitoring
        logger.info(
            "call_tool(%s) completed in %.2fms (target <300ms)",
            tool_name,
            latency_ms,
        )

        return ToolCallResult(
            content=list(result.content),
            is_error=result.isError,
            latency_ms=latency_ms,
        )

    # ── Health check ─────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Send a ping to the MCP server to check connectivity.

        Returns:
            True if the server responds, False otherwise.
        """
        if not self._connected or self._session is None:
            return False
        try:
            await self._session.send_ping()
            return True
        except Exception:
            return False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        """Raise MCPConnectionError if not connected."""
        if not self._connected or self._session is None:
            raise MCPConnectionError(
                "Not connected to OpenViking MCP server. Call connect() first."
            )

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected to the server."""
        return self._connected


# ─────────────────────────────────────────────────────────────────────────────
# Module-level factory and singleton
# ─────────────────────────────────────────────────────────────────────────────

_openviking_config: OpenVikingConfig | None = None


def configure_openviking(config: OpenVikingConfig) -> None:
    """Configure the module-level OpenViking config (singleton).

    This config will be used by get_mcp_client() and get_mcp_client_context().

    Args:
        config: OpenViking configuration instance.
    """
    global _openviking_config
    _openviking_config = config
    logger.info("OpenViking MCP client configured: command=%s", config.command)


def get_openviking_config() -> OpenVikingConfig | None:
    """Return the current OpenViking configuration, or None if not configured."""
    return _openviking_config


def get_mcp_client() -> MCPClient:
    """Get a new MCPClient instance with the configured OpenViking settings.

    Note: Caller is responsible for managing the client lifecycle (connect/disconnect).
    Prefer using get_mcp_client_context() for automatic lifecycle management.

    Returns:
        MCPClient instance (not connected until connect() is called).
    """
    if _openviking_config is None:
        logger.warning(
            "OpenViking not configured - returning unconfigured MCPClient. "
            "Call will fail until configure_openviking() is called."
        )
        return MCPClient(OpenVikingConfig())
    return MCPClient(_openviking_config)


async def get_mcp_client_connected() -> MCPClient:
    """Get a connected MCPClient instance.

    This is a convenience function that creates a client and connects it.

    Returns:
        Connected MCPClient instance.

    Raises:
        MCPConnectionError: If connection fails.
    """
    client = get_mcp_client()
    await client.connect()
    return client
