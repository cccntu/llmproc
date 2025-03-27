"""Tests for the enhanced file descriptor API."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from llmproc.program import LLMProgram
from llmproc.llm_process import LLMProcess
from llmproc.tools.file_descriptor import FileDescriptorManager, read_fd_tool, fd_to_file_tool
from llmproc.tools.tool_result import ToolResult


class TestEnhancedFileDescriptorAPI:
    """Tests for the enhanced file descriptor API."""

    def test_extract_to_new_fd(self):
        """Test extracting content to a new file descriptor."""
        manager = FileDescriptorManager()
        
        # Create multi-line content that spans multiple pages
        content = "\n".join([f"Line {i}" for i in range(1, 101)])
        
        # Set small page size to force pagination
        manager.default_page_size = 100
        
        # Create first FD
        fd_result = manager.create_fd(content)
        fd_id = fd_result.content.split('fd="')[1].split('"')[0]
        
        # Extract page 2 to a new file descriptor
        extract_result = manager.read_fd(fd_id, page=2, extract_to_new_fd=True)
        
        # Check that the result has the right format
        assert "<fd_extraction " in extract_result.content
        assert "new_fd" in extract_result.content
        
        # Extract the new FD ID
        new_fd_id = extract_result.content.split('new_fd="')[1].split('"')[0]
        
        # Check the new FD exists
        assert new_fd_id in manager.file_descriptors
        
        # Read from the new FD to verify content
        new_fd_content = manager.read_fd(new_fd_id, read_all=True)
        
        # Verify content from new FD is similar to what we'd get from reading page 2
        page2_content = manager.read_fd(fd_id, page=2)
        
        # Extract actual content from XML result
        page2_text = page2_content.content.split('>\n')[1].split('\n</fd_content')[0]
        new_fd_text = new_fd_content.content.split('>\n')[1].split('\n</fd_content')[0]
        
        # They should contain similar content
        assert len(new_fd_text) > 0
        assert new_fd_text == page2_text

    def test_extract_entire_content(self):
        """Test extracting entire content to a new file descriptor."""
        manager = FileDescriptorManager()
        
        # Create content
        content = "This is test content that will be extracted to a new FD"
        
        # Create first FD
        fd_result = manager.create_fd(content)
        fd_id = fd_result.content.split('fd="')[1].split('"')[0]
        
        # Extract all content to a new file descriptor
        extract_result = manager.read_fd(fd_id, read_all=True, extract_to_new_fd=True)
        
        # Extract the new FD ID
        new_fd_id = extract_result.content.split('new_fd="')[1].split('"')[0]
        
        # Read from the new FD to verify content
        new_fd_content = manager.read_fd(new_fd_id, read_all=True)
        new_fd_text = new_fd_content.content.split('>\n')[1].split('\n</fd_content')[0]
        
        # Should contain the entire original content
        assert new_fd_text == content


@pytest.mark.asyncio
async def test_read_fd_tool_with_extraction():
    """Test the read_fd tool function with extraction to new FD."""
    # Mock LLMProcess with fd_manager
    process = Mock()
    process.fd_manager = Mock()
    
    # Mock FD manager response for extraction
    process.fd_manager.read_fd.return_value = ToolResult(
        content='<fd_extraction source_fd="fd:1" new_fd="fd:2" page="1" content_size="100">\n'
                '  <message>Content from fd:1 has been extracted to fd:2</message>\n'
                '</fd_extraction>'
    )
    
    # Call the tool with extract_to_new_fd=True
    result = await read_fd_tool(
        fd="fd:1", 
        page=2, 
        extract_to_new_fd=True, 
        llm_process=process
    )
    
    # Verify fd_manager.read_fd was called with correct args
    process.fd_manager.read_fd.assert_called_once_with(
        "fd:1", 
        page=2, 
        read_all=False, 
        extract_to_new_fd=True
    )
    
    # Check result
    assert "Content from fd:1 has been extracted to fd:2" in result.content


@pytest.mark.asyncio
async def test_fd_to_file_modes():
    """Test fd_to_file with different modes."""
    # Create temporary files for testing
    import tempfile
    import os
    
    # Mock process with FD manager
    process = Mock()
    process.fd_manager = FileDescriptorManager()
    process.file_descriptor_enabled = True
    
    # Create test content
    test_content = "This is test content for fd_to_file modes"
    
    # Create a file descriptor
    fd_result = process.fd_manager.create_fd(test_content)
    fd_id = fd_result.content.split('fd="')[1].split('"')[0]
    
    # Use a temporary directory for the test files
    with tempfile.TemporaryDirectory() as temp_dir:
        # Test write mode (default)
        file_path_write = os.path.join(temp_dir, "test_write.txt")
        write_result = await fd_to_file_tool(
            fd=fd_id,
            file_path=file_path_write,
            llm_process=process
        )
        
        # Verify the file was created with the content
        assert os.path.exists(file_path_write)
        with open(file_path_write, 'r') as f:
            content = f.read()
            assert content == test_content
        
        # Test append mode
        file_path_append = os.path.join(temp_dir, "test_append.txt")
        
        # First write to create the file
        await fd_to_file_tool(
            fd=fd_id,
            file_path=file_path_append,
            llm_process=process
        )
        
        # Then append to it
        append_result = await fd_to_file_tool(
            fd=fd_id,
            file_path=file_path_append,
            mode="append",
            llm_process=process
        )
        
        # Verify content was appended
        with open(file_path_append, 'r') as f:
            content = f.read()
            assert content == test_content + test_content
        
        # Check that mode is reported in the result
        assert "mode=\"append\"" in append_result.content


@pytest.mark.asyncio
async def test_fd_integration_end_to_end():
    """Test integration of the enhanced file descriptor API with the system."""
    # Mock the provider client to avoid actual API calls
    with patch("llmproc.providers.providers.get_provider_client") as mock_get_provider:
        mock_client = Mock()
        mock_get_provider.return_value = mock_client
        
        # Create a program with file descriptor support
        program = Mock(spec=LLMProgram)
        program.model_name = "model"
        program.provider = "anthropic"
        program.tools = {"enabled": ["read_fd"]}
        program.system_prompt = "system"
        program.display_name = "display"
        program.base_dir = None
        program.api_params = {}
        program.get_enriched_system_prompt = Mock(return_value="enriched")
        
        # Create a process
        process = LLMProcess(program=program)
        
        # Manually enable file descriptors
        process.file_descriptor_enabled = True
        process.fd_manager = FileDescriptorManager()
        
        # Create a file descriptor with test content
        test_content = "This is test content for fd extraction\n" * 10
        fd_result = process.fd_manager.create_fd(test_content)
        fd_id = fd_result.content.split('fd="')[1].split('"')[0]
        
        # Mock the registry and tool handlers
        from llmproc.tools import ToolRegistry
        registry = ToolRegistry()
        from llmproc.tools import register_file_descriptor_tools
        register_file_descriptor_tools(registry, process)
        
        # Get the read_fd handler
        handler = registry.get_handler("read_fd")
        
        # Call the handler with extract_to_new_fd=True
        result = await handler({
            "fd": fd_id,
            "page": 1,
            "extract_to_new_fd": True
        })
        
        # Check result format
        assert "<fd_extraction" in result.content
        assert "new_fd" in result.content
        
        # Extract the new FD ID from the result
        new_fd_id = result.content.split('new_fd="')[1].split('"')[0]
        
        # Verify the new FD exists
        assert new_fd_id in process.fd_manager.file_descriptors
        
        
@pytest.mark.asyncio
async def test_enhanced_fd_workflow():
    """Test a complete enhanced FD workflow with typical operations sequence."""
    import tempfile
    import os
    
    # Create a temporary directory for file operations
    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup a process with FD manager
        process = Mock()
        process.fd_manager = FileDescriptorManager(default_page_size=100)
        process.file_descriptor_enabled = True
        
        # Create registry and register tools
        from llmproc.tools import ToolRegistry
        registry = ToolRegistry()
        from llmproc.tools import register_file_descriptor_tools
        register_file_descriptor_tools(registry, process)
        
        # 1. Create sample content with multiple pages
        content = "# Sample Document\n\n"
        # Add introduction section
        content += "## Introduction\n" + ("This is introduction content.\n" * 20)
        # Add methodology section
        content += "\n## Methodology\n" + ("This is methodology content.\n" * 20)
        # Add results section
        content += "\n## Results\n" + ("This is results content.\n" * 20)
        # Add conclusion section
        content += "\n## Conclusion\n" + ("This is conclusion content.\n" * 20)
        
        # 2. Create initial file descriptor
        fd_result = process.fd_manager.create_fd(content)
        original_fd_id = fd_result.content.split('fd="')[1].split('"')[0]
        
        # 3. Typical workflow - first READ to examine
        # Get handler for read_fd
        read_handler = registry.get_handler("read_fd")
        
        # Read the first page to explore content
        page1_result = await read_handler({
            "fd": original_fd_id,
            "page": 1
        })
        
        # Verify page 1 contains introduction
        assert "Introduction" in page1_result.content
        
        # Read additional pages to find content of interest
        page2_result = await read_handler({
            "fd": original_fd_id,
            "page": 2
        })
        
        # Check if page 2 contains methodology
        page2_has_methodology = "Methodology" in page2_result.content
        
        # Read page 3 if needed
        page3_result = await read_handler({
            "fd": original_fd_id,
            "page": 3
        })
        
        # Determine which page has results section
        target_page = 3  # Assume page 3 has results
        if "Results" in page2_result.content:
            target_page = 2
        elif "Results" in page1_result.content:
            target_page = 1
        
        # 4. Next step in workflow - EXTRACT the page with results to a new FD
        extract_result = await read_handler({
            "fd": original_fd_id,
            "page": target_page,
            "extract_to_new_fd": True
        })
        
        # Verify extraction occurred and get new FD ID
        assert "<fd_extraction" in extract_result.content
        results_fd_id = extract_result.content.split('new_fd="')[1].split('"')[0]
        assert results_fd_id in process.fd_manager.file_descriptors
        
        # 5. Read the extracted content to verify
        extracted_content_result = await read_handler({
            "fd": results_fd_id,
            "read_all": True
        })
        
        # Verify extracted content has results section
        assert "Results" in extracted_content_result.content
        
        # 6. Write the extracted content to a file
        get_fd_to_file_handler = registry.get_handler("fd_to_file")
        output_file = os.path.join(temp_dir, "results_section.md")
        
        write_result = await get_fd_to_file_handler({
            "fd": results_fd_id,
            "file_path": output_file
        })
        
        # Verify file was written
        assert os.path.exists(output_file)
        with open(output_file, 'r') as f:
            file_content = f.read()
            assert "Results" in file_content
            
        # 7. Create a combined report by extracting and appending multiple sections
        
        # Extract conclusion section (assumed to be on the last page)
        last_page = process.fd_manager.file_descriptors[original_fd_id]["total_pages"]
        conclusion_extract_result = await read_handler({
            "fd": original_fd_id,
            "page": last_page,
            "extract_to_new_fd": True
        })
        
        conclusion_fd_id = conclusion_extract_result.content.split('new_fd="')[1].split('"')[0]
        
        # Create report file with results first
        report_file = os.path.join(temp_dir, "report.md")
        await get_fd_to_file_handler({
            "fd": results_fd_id,
            "file_path": report_file
        })
        
        # Append conclusion
        append_result = await get_fd_to_file_handler({
            "fd": conclusion_fd_id,
            "file_path": report_file,
            "mode": "append"
        })
        
        # Verify combined report
        assert "mode=\"append\"" in append_result.content
        with open(report_file, 'r') as f:
            report_content = f.read()
            assert "Results" in report_content
            assert "Conclusion" in report_content