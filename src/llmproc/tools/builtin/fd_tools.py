"""Tool implementations for the file descriptor system.

Provides the read_fd and fd_to_file tools for interacting with file descriptors.
These tools handle the ToolResult wrapping around the plain data returned by
FileDescriptorManager's methods.
"""

import logging
from typing import Any, Dict, Optional

from llmproc.common.results import ToolResult
from llmproc.file_descriptors.formatter import format_fd_error
from llmproc.tools.context_aware import context_aware

# Set up logger
logger = logging.getLogger(__name__)


@context_aware
async def read_fd_tool(
    fd: str,
    read_all: bool = False,
    extract_to_new_fd: bool = False,
    mode: str = "page",
    start: int = 1,
    count: int = 1,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Read content from a file descriptor.
    
    Args:
        fd: File descriptor ID to read from (e.g., "fd:12345" or "ref:example_id")
        read_all: If true, returns the entire content
        extract_to_new_fd: If true, extracts content to a new file descriptor
        mode: Positioning mode: "page" (default), "line", or "char"
        start: Starting position (page number, line number, or character position)
        count: Number of units to read (pages, lines, or characters)
        runtime_context: Runtime context dictionary containing dependencies needed by the tool.
            Required keys: 'fd_manager' (FileDescriptorManager instance)
            
    Returns:
        ToolResult with content or a new file descriptor reference
    """
    # Get fd_manager from runtime context
    if not runtime_context or "fd_manager" not in runtime_context:
        error_msg = "File descriptor operations require runtime_context with fd_manager"
        logger.error(f"READ_FD ERROR: {error_msg}")
        return ToolResult.from_error(error_msg)
        
    fd_manager = runtime_context["fd_manager"]
        
    try:
        xml_content = fd_manager.read_fd_content(
            fd_id=fd,
            read_all=read_all,
            extract_to_new_fd=extract_to_new_fd,
            mode=mode,
            start=start,
            count=count
        )
        # Wrap successful result
        return ToolResult.from_success(xml_content)
    except KeyError as e:
        # Handle file descriptor not found
        error_msg = str(e)
        xml_error = format_fd_error("not_found", fd, error_msg)
        return ToolResult.from_error(xml_error)
    except ValueError as e:
        # Handle invalid parameters
        error_msg = str(e)
        xml_error = format_fd_error("invalid_page", fd, error_msg)
        return ToolResult.from_error(xml_error)
    except Exception as e:
        # Handle other errors
        error_msg = f"Error reading file descriptor: {str(e)}"
        logger.error(f"READ_FD ERROR: {error_msg}")
        logger.debug("Detailed traceback:", exc_info=True)
        xml_error = format_fd_error("read_error", fd, error_msg)
        return ToolResult.from_error(xml_error)


@context_aware
async def fd_to_file_tool(
    fd: str,
    file_path: str,
    mode: str = "write",
    create: bool = True,
    exist_ok: bool = True,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Write file descriptor content to a file on disk.

    Args:
        fd: File descriptor ID to export (e.g., "fd:12345" or "ref:example_id")
        file_path: Absolute path to the file to write
        mode: "write" (default) or "append"
        create: Create file if it doesn't exist (default: True)
        exist_ok: Allow overwriting existing file (default: True)
        runtime_context: Runtime context dictionary containing dependencies needed by the tool.
            Required keys: 'fd_manager' (FileDescriptorManager instance)

    Returns:
        ToolResult with success or error information
    """
    # Get fd_manager from runtime context
    if not runtime_context or "fd_manager" not in runtime_context:
        error_msg = "File descriptor operations require runtime_context with fd_manager"
        logger.error(f"FD_TO_FILE ERROR: {error_msg}")
        return ToolResult.from_error(error_msg)
        
    fd_manager = runtime_context["fd_manager"]
        
    try:
        xml_content = fd_manager.write_fd_to_file_content(
            fd_id=fd, 
            file_path=file_path, 
            mode=mode, 
            create=create, 
            exist_ok=exist_ok
        )
        # Wrap successful result
        return ToolResult.from_success(xml_content)
    except KeyError as e:
        # Handle file descriptor not found
        error_msg = str(e)
        xml_error = format_fd_error("not_found", fd, error_msg)
        return ToolResult.from_error(xml_error)
    except ValueError as e:
        # Handle invalid parameters
        error_msg = str(e)
        xml_error = format_fd_error("invalid_parameter", fd, error_msg)
        return ToolResult.from_error(xml_error)
    except Exception as e:
        # Handle other errors
        error_msg = f"Error writing file descriptor to file: {str(e)}"
        logger.error(f"FD_TO_FILE ERROR: {error_msg}")
        logger.debug("Detailed traceback:", exc_info=True)
        xml_error = format_fd_error("write_error", fd, error_msg)
        return ToolResult.from_error(xml_error)