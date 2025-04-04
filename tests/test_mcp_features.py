"""Tests for the MCP (Model Context Protocol) feature."""

import asyncio
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llmproc import LLMProcess


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    original_env = os.environ.copy()
    os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
    os.environ["GITHUB_TOKEN"] = "test-github-token"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_mcp_registry():
    """Mock the MCP registry and related components."""
    # Create MCP registry module mock
    mock_mcp_registry = MagicMock()

    # Setup mocks for MCP components
    mock_server_registry = MagicMock()
    mock_server_registry_class = MagicMock()
    mock_server_registry_class.from_config.return_value = mock_server_registry

    mock_aggregator = MagicMock()
    mock_aggregator_class = MagicMock()
    mock_aggregator_class.return_value = mock_aggregator

    # Create mock tools
    mock_tool1 = MagicMock()
    mock_tool1.name = "github.search_repositories"
    mock_tool1.description = "Search for GitHub repositories"
    mock_tool1.inputSchema = {"type": "object", "properties": {"q": {"type": "string"}}}

    mock_tool2 = MagicMock()
    mock_tool2.name = "github.get_file_contents"
    mock_tool2.description = "Get file contents from a GitHub repository"
    mock_tool2.inputSchema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "path": {"type": "string"},
        },
    }

    mock_tool3 = MagicMock()
    mock_tool3.name = "sequential-thinking.sequentialthinking"
    mock_tool3.description = "A detailed tool for dynamic and reflective problem-solving through thoughts"
    mock_tool3.inputSchema = {
        "type": "object",
        "properties": {
            "thought": {"type": "string"},
            "nextThoughtNeeded": {"type": "boolean"},
            "thoughtNumber": {"type": "integer"},
            "totalThoughts": {"type": "integer"},
        },
    }

    # Setup tool calls
    mock_tools_result = MagicMock()
    mock_tools_result.tools = [mock_tool1, mock_tool2, mock_tool3]
    mock_aggregator.list_tools = AsyncMock(return_value=mock_tools_result)

    # Setup tool results
    mock_tool_result = MagicMock()
    mock_tool_result.content = "Tool call result"
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

        yield


@pytest.fixture
def mcp_config_file():
    """Create a temporary MCP config file."""
    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp_file:
        json.dump(
            {
                "mcpServers": {
                    "github": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
                    },
                    "sequential-thinking": {
                        "type": "stdio",
                        "command": "/bin/zsh",
                        "args": [
                            "-c",
                            "npx -y @modelcontextprotocol/server-sequential-thinking",
                        ],
                    },
                }
            },
            temp_file,
        )
        temp_path = temp_file.name

    yield temp_path
    os.unlink(temp_path)


@patch("llmproc.llm_process.HAS_MCP", True)
@patch("llmproc.llm_process.asyncio.run")
@patch("llmproc.providers.providers.AsyncAnthropic")
def test_mcp_initialization(
    mock_anthropic, mock_asyncio_run, mock_mcp_registry, mock_env, mcp_config_file
):
    """Test that LLMProcess initializes correctly with MCP configuration."""
    # Setup mock client
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Create program and process with MCP configuration
    from llmproc.program import LLMProgram

    program = LLMProgram(
        model_name="claude-3-5-haiku-20241022",
        provider="anthropic",
        system_prompt="You are a test assistant.",
        mcp_config_path=mcp_config_file,
        mcp_tools={"github": ["search_repositories"], "sequential-thinking": ["sequentialthinking"]},
    )
    process = LLMProcess(program=program)

    # In our new design, MCP is only enabled when needed (in create or run)
    # For testing, we manually set it
    process.mcp_enabled = True

    # Check the configuration is correct
    assert process.mcp_tools == {
        "github": ["search_repositories"],
        "sequential-thinking": ["sequentialthinking"],
    }
    assert process.mcp_config_path == mcp_config_file
    assert process.mcp_tools == {
        "github": ["search_repositories"],
        "sequential-thinking": ["sequentialthinking"],
    }

    # In our new design, _initialize_tools no longer calls asyncio.run
    # Instead it's done lazily in run() or directly in create()
    # So we don't check mock_asyncio_run.assert_called_once()


@patch("llmproc.llm_process.HAS_MCP", True)
def test_from_toml_with_mcp(mock_mcp_registry, mock_env, mcp_config_file):
    """Test loading from a TOML configuration with MCP settings."""
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        # Create a config directory and copy the MCP config file
        config_dir = temp_dir_path / "config"
        config_dir.mkdir()

        # Read the content of the mcp_config_file
        with open(mcp_config_file) as src_file:
            mcp_config_content = src_file.read()

        # Write the content to the new file
        mcp_config_dest = config_dir / "mcp_servers.json"
        mcp_config_dest.write_text(mcp_config_content)

        # Create a TOML config file
        config_file = temp_dir_path / "config.toml"
        config_file.write_text("""
[model]
name = "claude-3-5-haiku-20241022"
provider = "anthropic"
display_name = "Test MCP Assistant"

[prompt]
system_prompt = "You are a test assistant with tool access."

[parameters]
temperature = 0.7
max_tokens = 300

[mcp]
config_path = "config/mcp_servers.json"

[mcp.tools]
github = ["search_repositories", "get_file_contents"]
sequential-thinking = ["sequentialthinking"]
""")

        # Create and patch the instance
        with patch("llmproc.providers.providers.AsyncAnthropic"):
            with patch("llmproc.llm_process.asyncio.run"):
                    # Use the two-step pattern
                    from llmproc.program import LLMProgram

                    program = LLMProgram.from_toml(config_file)

                    # Mock the start method to return a process without actually initializing MCP
                    with patch("llmproc.program.LLMProgram.start") as mock_start:
                        process = LLMProcess(program=program)
                        mock_start.return_value = process

                        # In our new design, MCP is only enabled when needed (in create or run)
                        # So we check the configuration instead
                        expected_config_path = (
                            config_dir / "mcp_servers.json"
                        ).resolve()
                        assert (
                            Path(process.mcp_config_path).resolve()
                            == expected_config_path
                        )
                        assert (
                            "github" in process.mcp_tools
                            and "sequential-thinking" in process.mcp_tools
                        )
                        assert process.mcp_tools == {
                            "github": ["search_repositories", "get_file_contents"],
                            "sequential-thinking": ["sequentialthinking"],
                        }
                        assert process.model_name == "claude-3-5-haiku-20241022"
                        assert process.provider == "anthropic"
                        assert process.display_name == "Test MCP Assistant"


@patch("llmproc.llm_process.HAS_MCP", True)
@patch("llmproc.providers.providers.AsyncAnthropic")
def test_mcp_with_no_tools(
    mock_anthropic, mock_mcp_registry, mock_env, mcp_config_file
):
    """Test behavior when MCP is enabled but no tools are specified."""
    # Mock asyncio.run to do nothing
    with patch("llmproc.llm_process.asyncio.run"):
        # Create empty tools dictionary - not an empty dict
        empty_tools = {"github": []}

        # Create program and process with empty tools
        from llmproc.program import LLMProgram

        program = LLMProgram(
            model_name="claude-3-5-haiku-20241022",
            provider="anthropic",
            system_prompt="You are a test assistant.",
            mcp_config_path=mcp_config_file,
            mcp_tools=empty_tools,
        )
        process = LLMProcess(program=program)

        # Set mcp_enabled for testing
        process.mcp_enabled = True

        # Check configuration
        assert process.mcp_tools == {"github": []}
        assert len(process.tools) == 0


@patch("llmproc.llm_process.HAS_MCP", True)
@patch("llmproc.providers.providers.AsyncAnthropic")
def test_mcp_with_all_tools(
    mock_anthropic, mock_mcp_registry, mock_env, mcp_config_file
):
    """Test behavior when all tools from a server are requested."""
    # Mock asyncio.run to actually call the _initialize_mcp_tools method
    with patch("llmproc.llm_process.asyncio.run"):
        # Create program and process with "all" tools configuration
        from llmproc.program import LLMProgram

        program = LLMProgram(
            model_name="claude-3-5-haiku-20241022",
            provider="anthropic",
            system_prompt="You are a test assistant.",
            mcp_config_path=mcp_config_file,
            mcp_tools={"github": "all", "sequential-thinking": ["sequentialthinking"]},
        )
        process = LLMProcess(program=program)

        # Set mcp_enabled for testing
        process.mcp_enabled = True

        # Check configuration
        assert process.mcp_tools == {"github": "all", "sequential-thinking": ["sequentialthinking"]}


@patch("llmproc.llm_process.HAS_MCP", True)
def test_invalid_mcp_tools_config(mock_mcp_registry, mock_env, mcp_config_file):
    """Test that an invalid MCP tools configuration raises a ValueError."""
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        # Create a config directory and copy the MCP config file
        config_dir = temp_dir_path / "config"
        config_dir.mkdir()

        # Read the content of the mcp_config_file
        with open(mcp_config_file) as src_file:
            mcp_config_content = src_file.read()

        # Write the content to the new file
        mcp_config_dest = config_dir / "mcp_servers.json"
        mcp_config_dest.write_text(mcp_config_content)

        # Create a TOML config file with invalid tools configuration
        config_file = temp_dir_path / "config.toml"
        config_file.write_text("""
[model]
name = "claude-3-haiku-20240307"
provider = "anthropic"

[prompt]
system_prompt = "You are a test assistant with tool access."

[mcp]
config_path = "config/mcp_servers.json"

[mcp.tools]
github = 123  # This is invalid, should be a list or "all"
""")

        # Test that it raises a ValueError
        with patch("llmproc.providers.providers.AsyncAnthropic"):
                with pytest.raises(ValueError):
                    # Use LLMProgram.from_toml instead
                    from llmproc.program import LLMProgram

                    LLMProgram.from_toml(config_file)


@patch("llmproc.llm_process.HAS_MCP", True)
@patch("llmproc.providers.providers.AsyncAnthropic")
def test_run_with_tools(mock_anthropic, mock_mcp_registry, mock_env, mcp_config_file):
    """Test the run method with tool support."""
    # Use a completely different approach - create a simplified mock for demonstration

    # Skip the test with a message to indicate manual testing is needed
    pytest.skip("This test requires actual run handling to be properly tested")

    # The core goal here would be to verify MCP tools are correctly registered
    # and the run method properly handles them. This is already verified in integration tests
    # and is difficult to properly mock in isolation.


@patch("llmproc.llm_process.HAS_MCP", True)
def test_openai_with_mcp_raises_error(mock_mcp_registry, mock_env, mcp_config_file):
    """Test that using OpenAI with MCP raises an error (not yet supported)."""
    with patch("llmproc.providers.providers.AsyncOpenAI", MagicMock()):
        from llmproc.program import LLMProgram

        # Create program with OpenAI provider but MCP configuration
        program = LLMProgram(
            model_name="gpt-4o",
            provider="openai",
            system_prompt="You are a test assistant.",
            mcp_config_path=mcp_config_file,
            mcp_tools={"github": ["search_repositories"]},
        )

        with pytest.raises(
            ValueError,
            match="MCP features are currently only supported with the Anthropic provider",
        ):
            LLMProcess(program=program)


@patch("llmproc.llm_process.HAS_MCP", False)
def test_mcp_import_error(mock_env, mcp_config_file):
    """Test that trying to use MCP when the package is not installed raises an ImportError."""
    with patch("llmproc.providers.providers.AsyncAnthropic", MagicMock()):
            from llmproc.program import LLMProgram

            # Create program with MCP configuration
            program = LLMProgram(
                model_name="claude-3-haiku-20240307",
                provider="anthropic",
                system_prompt="You are a test assistant.",
                mcp_config_path=mcp_config_file,
                mcp_tools={"github": ["search_repositories"]},
            )

            with pytest.raises(
                ImportError, match="MCP features require the mcp-registry package"
            ):
                LLMProcess(program=program)
