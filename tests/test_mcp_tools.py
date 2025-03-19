"""Tests for MCP tool execution."""

import asyncio
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llmproc import LLMProcess
from llmproc.providers.anthropic_tools import (
    format_tool_result,
    process_response_content,
)


@pytest.fixture
def mock_time_response():
    """Mock response for the time tool."""

    class ToolResponse:
        def __init__(self, time_data):
            self.content = time_data
            self.isError = False

    return ToolResponse(
        {
            "unix_timestamp": 1646870400,
            "utc_time": "2022-03-10T00:00:00Z",
            "timezone": "UTC",
        }
    )


@pytest.fixture
def time_mcp_config():
    """Create a temporary MCP config file with time server."""
    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
        json.dump(
            {
                "mcpServers": {
                    "time": {
                        "type": "stdio",
                        "command": "uvx",
                        "args": ["mcp-server-time"],
                    }
                }
            },
            temp_file,
        )
        temp_path = temp_file.name

    yield temp_path
    os.unlink(temp_path)


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    original_env = os.environ.copy()
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_mcp_registry():
    """Mock the MCP registry with time tool."""
    # Create MCP registry module mock
    mock_mcp_registry = MagicMock()

    # Setup mocks for MCP components
    mock_server_registry = MagicMock()
    mock_server_registry_class = MagicMock()
    mock_server_registry_class.from_config.return_value = mock_server_registry

    mock_aggregator = MagicMock()
    mock_aggregator_class = MagicMock()
    mock_aggregator_class.return_value = mock_aggregator

    # Create mock time tool
    mock_tool = MagicMock()
    mock_tool.name = "time.current"
    mock_tool.description = "Get the current time"
    mock_tool.inputSchema = {"type": "object", "properties": {}}

    # Setup tool calls
    mock_tools_result = MagicMock()
    mock_tools_result.tools = [mock_tool]
    mock_aggregator.list_tools = AsyncMock(return_value=mock_tools_result)

    # Setup tool results
    mock_tool_result = MagicMock()
    mock_tool_result.content = {
        "unix_timestamp": 1646870400,
        "utc_time": "2022-03-10T00:00:00Z",
        "timezone": "UTC",
    }
    mock_tool_result.isError = False
    mock_aggregator.call_tool = AsyncMock(return_value=mock_tool_result)

    # Create patches for the mcp_registry module
    with patch.dict(
        "sys.modules",
        {
            "mcp_registry": mock_mcp_registry,
        },
    ):
        # Set attributes on the mock module
        mock_mcp_registry.ServerRegistry = mock_server_registry_class
        mock_mcp_registry.MCPAggregator = mock_aggregator_class
        mock_mcp_registry.get_config_path = MagicMock(return_value="/mock/config/path")

        yield mock_aggregator


@pytest.mark.asyncio
@patch("llmproc.llm_process.HAS_MCP", True)
async def test_process_response_content(mock_mcp_registry, mock_time_response):
    """Test the process_response_content function directly."""

    # Create mock content
    class MockContent:
        def __init__(self, type_name, **kwargs):
            self.type = type_name
            for key, value in kwargs.items():
                setattr(self, key, value)

    text_content = MockContent("text", text="This is a test response")
    tool_content = MockContent("tool_use", name="time.current", input={}, id="tool1")

    content_list = [text_content, tool_content]

    # Mock the aggregator's call_tool
    mock_mcp_registry.call_tool = AsyncMock(return_value=mock_time_response)

    # Call the function
    tool_results = await process_response_content(
        content_list, mock_mcp_registry
    )

    # Assertions
    assert len(tool_results) == 1
    assert tool_results[0]["tool_use_id"] == "tool1"
    assert "unix_timestamp" in tool_results[0]["content"]
    assert not tool_results[0]["is_error"]


@patch("llmproc.llm_process.HAS_MCP", True)
@patch("llmproc.providers.providers.anthropic", MagicMock())
@patch("llmproc.providers.providers.Anthropic")
@patch("llmproc.llm_process.asyncio.run")
def test_llm_process_with_time_tool(
    mock_asyncio_run, mock_anthropic, mock_mcp_registry, mock_env, time_mcp_config
):
    """Test LLMProcess with the time tool."""
    # Setup mock client
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Create program and process with MCP configuration
    from llmproc.program import LLMProgram

    program = LLMProgram(
        model_name="claude-3-haiku-20240307",
        provider="anthropic",
        system_prompt="You are an assistant with access to tools.",
        mcp_config_path=time_mcp_config,
        mcp_tools={"time": ["current"]},
    )
    process = LLMProcess(program=program)

    # Set mcp_enabled for testing
    process.mcp_enabled = True

    # Check configuration
    assert process.mcp_tools == {"time": ["current"]}
    assert process.mcp_config_path == time_mcp_config
    assert process.mcp_tools == {"time": ["current"]}

    # In our new design, _initialize_tools no longer calls asyncio.run
    # Instead it's done lazily in run() or directly in create()
    # So we don't check mock_asyncio_run.assert_called_once()


@pytest.mark.asyncio
@patch("llmproc.llm_process.HAS_MCP", True)
@patch("llmproc.providers.providers.anthropic", MagicMock())
@patch("llmproc.providers.providers.Anthropic")
async def test_run_with_time_tool(
    mock_anthropic, mock_mcp_registry, mock_env, time_mcp_config
):
    """Test the async run method with the time tool."""
    # Setup mock client
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Mock run method directly to bypass internal implementation details
    # This is simpler than trying to mock the internal _run_anthropic_with_tools method
    with patch("llmproc.llm_process.asyncio.run"):
        # Create program and process with MCP configuration
        from llmproc.program import LLMProgram

        program = LLMProgram(
            model_name="claude-3-haiku-20240307",
            provider="anthropic",
            system_prompt="You are an assistant with access to tools.",
            mcp_config_path=time_mcp_config,
            mcp_tools={"time": ["current"]},
        )
        process = LLMProcess(program=program)

    # Import RunResult for mocking
    from llmproc.results import RunResult

    # Create a mock RunResult
    mock_run_result = RunResult()
    mock_run_result.api_calls = 1

    # Patch the _async_run method directly to return the mock RunResult
    process._async_run = AsyncMock(return_value=mock_run_result)

    # Patch get_last_message to return our expected response
    process.get_last_message = MagicMock(
        return_value="The current time is 2022-03-10T00:00:00Z"
    )

    # Call the run method
    result = await process.run("What time is it now?")

    # Assert the result is our mock RunResult
    assert isinstance(result, RunResult)
    assert result.api_calls == 1

    # Check that the _async_run method was called
    process._async_run.assert_called_once_with("What time is it now?", 10, None)

    # In our new API design, get_last_message is not called inside the run method.
    # It's the responsibility of the caller to extract the message when needed.
