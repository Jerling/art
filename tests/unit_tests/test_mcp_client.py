"""Unit tests for MCP Client and WeChatMessageService.

Tests cover:
- MCPClient connection lifecycle
- list_tools and call_tool operations
- Error handling
- WeChatMessageService integration
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.mcp_client import (
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
    OpenVikingConfig,
    ToolCallResult,
    ToolInfo,
    configure_openviking,
    get_mcp_client,
)
from src.services.wechat_message import (
    ToolExecutionResult,
    WeChatMessageContext,
    WeChatMessageService,
)


# ─────────────────────────────────────────────────────────────────────────────
# OpenVikingConfig Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenVikingConfig:
    def test_is_configured_with_command(self):
        config = OpenVikingConfig(command="/usr/bin/openviking")
        assert config.is_configured is True

    def test_is_not_configured_without_command(self):
        config = OpenVikingConfig()
        assert config.is_configured is False

    def test_is_not_configured_with_empty_string(self):
        config = OpenVikingConfig(command="")
        assert config.is_configured is False

    def test_default_values(self):
        config = OpenVikingConfig()
        assert config.command is None
        assert config.args == []
        assert config.env is None
        assert config.cwd is None
        assert config.timeout_seconds == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# ToolInfo Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestToolInfo:
    def test_from_mcp_tool(self):
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.inputSchema = {"type": "object", "properties": {"query": {"type": "string"}}}

        tool_info = ToolInfo.from_mcp_tool(mock_tool)
        assert tool_info.name == "test_tool"
        assert tool_info.description == "A test tool"
        assert tool_info.input_schema == {"type": "object", "properties": {"query": {"type": "string"}}}


# ─────────────────────────────────────────────────────────────────────────────
# ToolCallResult Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCallResult:
    def test_text_content_with_text_items(self):
        mock_item1 = MagicMock()
        mock_item1.text = "Hello"
        mock_item2 = MagicMock()
        mock_item2.text = "World"

        result = ToolCallResult(
            content=[mock_item1, mock_item2],
            is_error=False,
            latency_ms=50.0,
        )

        assert result.text_content == ["Hello", "World"]

    def test_first_text(self):
        mock_item = MagicMock()
        mock_item.text = "First"

        result = ToolCallResult(content=[mock_item], is_error=False, latency_ms=10.0)
        assert result.first_text == "First"

    def test_first_text_empty(self):
        result = ToolCallResult(content=[], is_error=False, latency_ms=0.0)
        assert result.first_text is None


# ─────────────────────────────────────────────────────────────────────────────
# MCPClient Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMCPClient:
    def test_unconfigured_client_is_not_connected(self):
        config = OpenVikingConfig()
        client = MCPClient(config)
        assert client.is_connected is False

    def test_ensure_connected_raises_when_not_connected(self):
        config = OpenVikingConfig()
        client = MCPClient(config)

        # Access private method for testing
        with pytest.raises(MCPConnectionError) as exc_info:
            client._ensure_connected()
        assert "Not connected" in str(exc_info.value)

    def test_configure_openviking_sets_global(self):
        config = OpenVikingConfig(command="/test/command")
        configure_openviking(config)

        # get_mcp_client should now use the configured config
        client = get_mcp_client()
        assert client._config.command == "/test/command"

    def test_get_mcp_client_without_config(self):
        # Reset global config
        import src.worker.mcp_client as mcp_module
        mcp_module._openviking_config = None

        client = get_mcp_client()
        assert client._config.is_configured is False


class TestMCPClientAsync:
    @pytest.mark.anyio
    async def test_unconfigured_connect_raises(self):
        config = OpenVikingConfig()
        client = MCPClient(config)

        with pytest.raises(MCPConnectionError) as exc_info:
            await client.connect()
        assert "not configured" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_disconnect_when_not_connected(self):
        config = OpenVikingConfig()
        client = MCPClient(config)

        await client.disconnect()
        assert client.is_connected is False

    @pytest.mark.anyio
    async def test_ping_when_not_connected(self):
        config = OpenVikingConfig()
        client = MCPClient(config)

        result = await client.ping()
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# WeChatMessageService Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestWeChatMessageContext:
    def test_basic_context(self):
        ctx = WeChatMessageContext(
            openid="test_openid",
            content="Hello world",
            msg_type="text",
        )
        assert ctx.openid == "test_openid"
        assert ctx.content == "Hello world"
        assert ctx.msg_type == "text"


class TestToolExecutionResult:
    def test_successful_result(self):
        mock_tool_result = MagicMock()
        mock_tool_result.is_error = False
        mock_tool_result.latency_ms = 50.0

        mock_call_result = MagicMock()
        mock_call_result.content = [mock_tool_result]
        mock_call_result.is_error = False
        mock_call_result.latency_ms = 50.0

        result = ToolExecutionResult(
            success=True,
            tool_name="test_tool",
            result=mock_call_result,
            latency_ms=50.0,
        )

        assert result.success is True
        assert result.tool_name == "test_tool"
        assert result.latency_ms == 50.0

    def test_failed_result(self):
        result = ToolExecutionResult(
            success=False,
            tool_name="test_tool",
            result=None,
            error="Connection failed",
        )

        assert result.success is False
        assert result.error == "Connection failed"


class TestWeChatMessageService:
    def test_service_initialization(self):
        mock_client = MagicMock()
        service = WeChatMessageService(mcp_client=mock_client)
        assert service._mcp_client is mock_client

    def test_service_initialization_without_client(self):
        service = WeChatMessageService()
        assert service._mcp_client is None

    @pytest.mark.anyio
    async def test_list_available_tools_caches(self):
        mock_client = MagicMock()
        mock_tools = [
            ToolInfo(name="tool1", description="Tool 1", input_schema={}),
            ToolInfo(name="tool2", description="Tool 2", input_schema={}),
        ]
        mock_client.list_tools = AsyncMock(return_value=mock_tools)

        service = WeChatMessageService(mcp_client=mock_client)
        tools = await service.list_available_tools()

        assert len(tools) == 2
        assert service._available_tools is tools  # Should be cached

        # Second call should use cache, not call list_tools again
        tools2 = await service.list_available_tools()
        assert tools2 is tools
        mock_client.list_tools.assert_called_once()

    @pytest.mark.anyio
    async def test_execute_tool_success(self):
        mock_result = MagicMock()
        mock_result.content = []
        mock_result.is_error = False
        mock_result.latency_ms = 50.0

        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.connect = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=mock_result)

        service = WeChatMessageService(mcp_client=mock_client)
        exec_result = await service.execute_tool("test_tool", {"arg": "value"})

        assert exec_result.success is True
        assert exec_result.tool_name == "test_tool"
        assert exec_result.latency_ms == 50.0

    @pytest.mark.anyio
    async def test_execute_tool_connection_failure(self):
        mock_client = MagicMock()
        mock_client.is_connected = False
        mock_client.connect = AsyncMock(side_effect=MCPConnectionError("Failed"))

        service = WeChatMessageService(mcp_client=mock_client)
        exec_result = await service.execute_tool("test_tool")

        assert exec_result.success is False
        assert exec_result.error is not None
        assert "Failed to connect" in exec_result.error


class TestWeChatMessageServiceParsing:
    def test_parse_tools_command(self):
        service = WeChatMessageService()

        ctx = WeChatMessageContext(
            openid="test",
            content="/tools",
            msg_type="text",
        )

        tool_name, args = service._parse_message_for_tool(ctx)
        assert tool_name == "list_tools"
        assert args is None

    def test_parse_search_command(self):
        service = WeChatMessageService()

        ctx = WeChatMessageContext(
            openid="test",
            content="/search hello world",
            msg_type="text",
        )

        tool_name, args = service._parse_message_for_tool(ctx)
        assert tool_name == "search"
        assert args == {"query": "hello world"}

    def test_parse_execute_command(self):
        service = WeChatMessageService()

        ctx = WeChatMessageContext(
            openid="test",
            content="/execute my_tool arg1 arg2",
            msg_type="text",
        )

        tool_name, args = service._parse_message_for_tool(ctx)
        assert tool_name == "my_tool"
        assert args == {"input": "arg1 arg2"}

    def test_parse_no_tool_trigger(self):
        service = WeChatMessageService()

        ctx = WeChatMessageContext(
            openid="test",
            content="Hello, how are you?",
            msg_type="text",
        )

        tool_name, args = service._parse_message_for_tool(ctx)
        assert tool_name is None
        assert args is None


class TestToolResultFormatting:
    def test_format_error_result(self):
        service = WeChatMessageService()

        exec_result = ToolExecutionResult(
            success=False,
            tool_name="test_tool",
            result=None,
            error="Tool not found",
        )

        formatted = service.format_tool_result_for_wechat(exec_result)
        assert "Tool execution failed" in formatted
        assert "Tool not found" in formatted

    def test_format_success_with_text(self):
        service = WeChatMessageService()

        # Create a proper mock for ToolCallResult with text content
        mock_text_item = MagicMock()
        mock_text_item.text = "Search found 5 results"

        mock_result = MagicMock()
        mock_result.content = [mock_text_item]  # Actual list, not MagicMock
        mock_result.is_error = False
        mock_result.latency_ms = 120.0
        mock_result.text_content = ["Search found 5 results"]

        exec_result = ToolExecutionResult(
            success=True,
            tool_name="search",
            result=mock_result,
            latency_ms=120.0,
        )

        formatted = service.format_tool_result_for_wechat(exec_result)
        assert "Search found 5 results" in formatted
        assert "120ms" in formatted

    def test_format_success_with_error_flag(self):
        """Test formatting when MCP call succeeded but tool returned an error.

        In this case:
        - success=True (connection/call succeeded)
        - result.is_error=True (tool execution itself returned an error)
        """
        service = WeChatMessageService()

        mock_text_item = MagicMock()
        mock_text_item.text = "Some error occurred"

        mock_result = MagicMock()
        mock_result.content = [mock_text_item]
        mock_result.is_error = True  # MCP tool returned an error
        mock_result.latency_ms = 30.0
        mock_result.text_content = ["Some error occurred"]

        exec_result = ToolExecutionResult(
            success=True,  # The call succeeded
            tool_name="test",
            result=mock_result,
            latency_ms=30.0,
        )

        formatted = service.format_tool_result_for_wechat(exec_result)
        assert "[Error]" in formatted
