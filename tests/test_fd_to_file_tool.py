"""Tests for the fd_to_file tool."""

import os
import pytest
import tempfile
from unittest.mock import Mock, patch

from llmproc.program import LLMProgram
from llmproc.llm_process import LLMProcess
from llmproc.tools.file_descriptor import FileDescriptorManager
from llmproc.tools.tool_result import ToolResult

from llmproc.tools.file_descriptor import fd_to_file_tool


@pytest.mark.asyncio
async def test_fd_to_file_tool():
    """Test the fd_to_file tool."""
    
    # Create a process with file descriptor support
    from tests.conftest import create_mock_llm_program
    program = create_mock_llm_program(enabled_tools=["read_fd", "fd_to_file"])
    
    # Create a process with mocked provider client
    with patch("llmproc.providers.providers.get_provider_client") as mock_get_provider:
        mock_get_provider.return_value = Mock()
        process = LLMProcess(program=program)
        
        # Manually enable file descriptors
        process.file_descriptor_enabled = True
        process.fd_manager = FileDescriptorManager()
        
        # Create a file descriptor with content
        test_content = "This is test content for fd_to_file tool"
        fd_result = process.fd_manager.create_fd(test_content)
        fd_id = fd_result.content.split('fd="')[1].split('"')[0]
        
        # Create temporary file path
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            tmp_path = tmp.name
        
        # Call the tool
        result = await fd_to_file_tool(fd=fd_id, file_path=tmp_path, llm_process=process)
    
    try:
        # Check result
        assert not result.is_error
        assert fd_id in result.content
        assert tmp_path in result.content
        
        # Verify file was created with correct content
        assert os.path.exists(tmp_path)
        with open(tmp_path, 'r') as f:
            content = f.read()
        assert content == test_content
    finally:
        # Clean up
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@pytest.mark.asyncio
async def test_fd_to_file_invalid_fd():
    """Test fd_to_file with an invalid file descriptor."""
    
    # Create a process with file descriptor support
    from tests.conftest import create_mock_llm_program
    program = create_mock_llm_program(enabled_tools=["read_fd", "fd_to_file"])
    
    # Create a process with mocked provider client
    with patch("llmproc.providers.providers.get_provider_client") as mock_get_provider:
        mock_get_provider.return_value = Mock()
        process = LLMProcess(program=program)
        
        # Manually enable file descriptors
        process.file_descriptor_enabled = True
        process.fd_manager = FileDescriptorManager()
        
        # Create temporary file path
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            tmp_path = tmp.name
        
        # Call the tool with invalid FD
        result = await fd_to_file_tool(fd="fd:999", file_path=tmp_path, llm_process=process)
    
    # Check result
    assert result.is_error
    assert "not found" in result.content


@pytest.mark.asyncio
async def test_fd_to_file_invalid_path():
    """Test fd_to_file with an invalid file path."""
    
    # Create a process with file descriptor support
    from tests.conftest import create_mock_llm_program
    program = create_mock_llm_program(enabled_tools=["read_fd", "fd_to_file"])
    
    # Create a process with mocked provider client
    with patch("llmproc.providers.providers.get_provider_client") as mock_get_provider:
        mock_get_provider.return_value = Mock()
        process = LLMProcess(program=program)
        
        # Manually enable file descriptors
        process.file_descriptor_enabled = True
        process.fd_manager = FileDescriptorManager()
        
        # Create a file descriptor with content
        test_content = "This is test content for fd_to_file tool"
        fd_result = process.fd_manager.create_fd(test_content)
        fd_id = fd_result.content.split('fd="')[1].split('"')[0]
        
        # Use an invalid path that should fail
        invalid_path = "/nonexistent/directory/file.txt"
        
        # Call the tool
        result = await fd_to_file_tool(fd=fd_id, file_path=invalid_path, llm_process=process)
    
    # Check result
    assert result.is_error
    assert "Error writing file descriptor" in result.content


@pytest.mark.asyncio
async def test_fd_to_file_no_process():
    """Test fd_to_file without a valid process."""
    
    # Call the tool without a process
    result = await fd_to_file_tool(fd="fd:1", file_path="test.txt")
    
    # Check result
    assert result.is_error
    assert "require" in result.content.lower()