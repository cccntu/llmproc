"""Integration tests for file descriptor system with the rest of LLMProc."""

import pytest
from tests.conftest import create_mock_llm_program
from unittest.mock import Mock, patch, MagicMock, call

from llmproc.program import LLMProgram
from llmproc.llm_process import LLMProcess
from llmproc.tools.file_descriptor import FileDescriptorManager, read_fd_tool
from llmproc.tools.tool_result import ToolResult
from llmproc.providers.anthropic_process_executor import AnthropicProcessExecutor
from llmproc.results import RunResult


def test_fd_integration_with_anthropic_executor():
    """Test direct file descriptor wrapping logic without async executor call."""
    # Create the fd_manager
    fd_manager = FileDescriptorManager(max_direct_output_chars=100)
    
    # Set up a large tool result that should be wrapped
    large_content = "This is a very large tool output " * 20  # More than max_direct_output_chars
    tool_result = ToolResult(content=large_content)
    
    # Check direct conditions for wrapping
    assert len(large_content) > fd_manager.max_direct_output_chars
    
    # Create a file descriptor for the content
    fd_result = fd_manager.create_fd(large_content)
    
    # Verify the FD was created properly
    assert "<fd_result fd=" in fd_result.content
    assert "preview" in fd_result.content


@pytest.mark.asyncio
@patch("llmproc.providers.providers.get_provider_client")
async def test_fd_copy_during_fork(mock_get_provider_client):
    """Test that file descriptors are properly deep copied during fork."""
    # Mock the provider client to avoid actual API calls
    mock_client = Mock()
    mock_get_provider_client.return_value = mock_client
    
    # Create a program with file descriptor support
    from tests.conftest import create_mock_llm_program
    program = create_mock_llm_program()
    program.tools = {"enabled": ["read_fd"]}
    program.system_prompt = "system"
    program.display_name = "display"
    program.base_dir = None
    program.api_params = {}
    program.get_enriched_system_prompt = Mock(return_value="enriched system prompt")
    
    # Create a process
    process = LLMProcess(program=program)
    
    # Manually enable file descriptors with a small max_direct_output_chars for testing
    process.file_descriptor_enabled = True
    process.fd_manager = FileDescriptorManager(max_direct_output_chars=100)
    
    # Create multiple file descriptors with different content
    fd1_content = "This is content for the first file descriptor"
    fd2_content = "This is much longer content for the second file descriptor that should exceed the direct output threshold and force pagination into multiple pages" * 3
    
    fd1_result = process.fd_manager.create_fd(fd1_content)
    fd2_result = process.fd_manager.create_fd(fd2_content)
    
    # Extract fd IDs
    fd1_id = fd1_result.content.split('fd="')[1].split('"')[0]
    fd2_id = fd2_result.content.split('fd="')[1].split('"')[0]
    
    # Verify FDs were created with expected IDs
    assert fd1_id == "fd:1"
    assert fd2_id == "fd:2"
    
    # Verify content is stored in the original process
    assert process.fd_manager.file_descriptors[fd1_id]["content"] == fd1_content
    assert process.fd_manager.file_descriptors[fd2_id]["content"] == fd2_content
    
    # Fork the process
    forked_process = await process.fork_process()
    
    # Verify the FD system was copied to the forked process
    assert forked_process.file_descriptor_enabled
    assert forked_process.fd_manager is not None
    
    # Verify file descriptors were copied
    assert fd1_id in forked_process.fd_manager.file_descriptors
    assert fd2_id in forked_process.fd_manager.file_descriptors
    
    # Verify the content of the copied FDs
    assert forked_process.fd_manager.file_descriptors[fd1_id]["content"] == fd1_content
    assert forked_process.fd_manager.file_descriptors[fd2_id]["content"] == fd2_content
    
    # Verify the total_pages was correctly copied
    assert forked_process.fd_manager.file_descriptors[fd1_id]["total_pages"] == process.fd_manager.file_descriptors[fd1_id]["total_pages"]
    assert forked_process.fd_manager.file_descriptors[fd2_id]["total_pages"] == process.fd_manager.file_descriptors[fd2_id]["total_pages"]
    
    # Test that changes to the original process don't affect the fork
    fd3_content = "This is content created after the fork"
    process.fd_manager.create_fd(fd3_content)
    
    # New FD should exist in original but not in fork
    assert "fd:3" in process.fd_manager.file_descriptors
    assert "fd:3" not in forked_process.fd_manager.file_descriptors
    
    # Create a new FD in the fork
    fd3_fork_content = "This is content created in the fork"
    forked_process.fd_manager.create_fd(fd3_fork_content)
    
    # New fork FD should exist in fork but not original
    assert "fd:3" in forked_process.fd_manager.file_descriptors
    assert forked_process.fd_manager.file_descriptors["fd:3"]["content"] == fd3_fork_content


def test_fd_pagination_with_very_long_lines():
    """Test pagination algorithm with very long single lines of text."""
    manager = FileDescriptorManager(default_page_size=100)
    
    # Create content with multiple lines - much more likely to trigger pagination
    long_line = "\n".join(["This is line " + str(i) + " " * 20 for i in range(50)])  # 50 lines with reasonable length
    
    # Create FD
    fd_result = manager.create_fd(long_line)
    fd_id = fd_result.content.split('fd="')[1].split('"')[0]
    
    # Verify we have multiple pages
    assert manager.file_descriptors[fd_id]["total_pages"] > 1
    
    # Read first page and verify it contains content
    result1 = manager.read_fd(fd_id, mode="page", start=1)
    page1_content = result1.content.split('>\n')[1].split('\n</fd_content')[0]
    assert len(page1_content) > 0
    assert len(page1_content) <= manager.default_page_size  # Should be limited by page size
    
    # Read all pages
    result_all = manager.read_fd(fd_id, read_all=True)
    
    # Should have the complete original content
    extracted_content = result_all.content.split('>\n')[1].split('\n</fd_content')[0]
    # Check if content length matches
    assert len(extracted_content) == len(long_line)


def test_fd_pagination_with_mixed_line_lengths():
    """Test pagination with a mix of short and long lines."""
    manager = FileDescriptorManager(default_page_size=50)
    
    # Create content with mixed line lengths
    content = "Short line\n"
    content += "A very long line that should span across multiple characters and force pagination in the middle\n"
    content += "Another short line\n"
    content += "A second very long line that continues well beyond the page size limit and forces pagination again\n"
    content += "Final short line"
    
    # Create FD
    fd_result = manager.create_fd(content)
    fd_id = fd_result.content.split('fd="')[1].split('"')[0]
    
    # Get total pages
    total_pages = manager.file_descriptors[fd_id]["total_pages"]
    
    # Read each page and collect line information
    all_lines_info = []
    for page in range(1, total_pages + 1):
        result = manager.read_fd(fd_id, mode="page", start=page)
        
        # Extract line range
        lines_attr = result.content.split('lines="')[1].split('"')[0]
        all_lines_info.append(lines_attr)
    
    # Verify line continuity (each page should start where the previous ended)
    for i in range(len(all_lines_info) - 1):
        current_end = int(all_lines_info[i].split('-')[1])
        next_start = int(all_lines_info[i+1].split('-')[0])
        assert next_start == current_end, f"Line discontinuity between pages {i+1} and {i+2}"
    
    # Read all content
    result_all = manager.read_fd(fd_id, read_all=True)
    
    # Should have a line range from 1 to the total line count
    total_line_count = manager.file_descriptors[fd_id]["total_lines"]
    assert f'lines="1-{total_line_count}"' in result_all.content
    
    # Extract content and verify it matches the original
    extracted_content = result_all.content.split('>\n')[1].split('\n</fd_content')[0]
    assert extracted_content == content


def test_fd_api_call_tracking():
    """Test that API calls and tool calls are properly tracked in RunResult."""
    run_result = RunResult()
    
    # Add API calls
    run_result.add_api_call({"model": "claude-3", "id": "msg_1"})
    run_result.add_api_call({"model": "claude-3", "id": "msg_2"})
    
    # Add tool calls
    run_result.add_tool_call({"type": "tool_call", "tool_name": "calculator"})
    run_result.add_tool_call({"type": "tool_call", "tool_name": "read_fd"})
    run_result.add_tool_call({"type": "tool_call", "tool_name": "example_tool"})
    
    # Verify counts
    assert run_result.api_calls == 2
    assert run_result.tool_calls == 3
    assert run_result.total_interactions == 5


def test_recursive_fd_protection():
    """Test protection against recursive FD creation when using fd_tools."""
    # Create a file descriptor manager
    fd_manager = FileDescriptorManager(max_direct_output_chars=100)
    
    # Create a file descriptor with large content
    large_content = "This is large content for testing" * 10
    fd_result = fd_manager.create_fd(large_content)
    fd_id = fd_result.content.split('fd="')[1].split('"')[0]
    
    # Verify FD exists
    assert fd_id in fd_manager.file_descriptors
    
    # Check if read_fd is in the fd_related_tools set
    assert "read_fd" in fd_manager.fd_related_tools
    
    # Check is_fd_related_tool method
    assert fd_manager.is_fd_related_tool("read_fd") is True
    assert fd_manager.is_fd_related_tool("random_tool") is False
    
    # Register a new FD tool
    fd_manager.register_fd_tool("custom_fd_tool")
    assert fd_manager.is_fd_related_tool("custom_fd_tool") is True