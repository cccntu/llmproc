"""Tools for LLMProcess.

This module provides system tools that can be used by LLMProcess instances.
It also provides a registry to retrieve tool handlers and schemas by name.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from . import mcp
from .calculator import calculator_tool, calculator_tool_def
from .file_descriptor import (
    fd_to_file_tool, fd_to_file_tool_def,
    file_descriptor_instructions, 
    read_fd_tool, read_fd_tool_def
)
from .fork import fork_tool, fork_tool_def
from .read_file import read_file_tool, read_file_tool_def
from .spawn import spawn_tool, spawn_tool_def
from .tool_result import ToolResult

# Set up logger
logger = logging.getLogger(__name__)


# Type definition for tool schemas
class ToolSchema(TypedDict):
    """Type definition for tool schema."""

    name: str
    description: str
    input_schema: dict[str, Any]


# Type definition for tool handler
ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class ToolRegistry:
    """Central registry for managing tools and their handlers.

    This class provides a unified interface for registering, accessing, and
    managing tools from different sources (system tools, MCP tools, etc.).
    """

    def __init__(self):
        """Initialize an empty tool registry."""
        self.tool_definitions = []  # Tool schemas for API calls
        self.tool_handlers = {}  # Mapping of tool names to handler functions

    def register_tool(
        self, name: str, handler: ToolHandler, definition: ToolSchema
    ) -> ToolSchema:
        """Register a tool with its handler and definition.

        Args:
            name: The name of the tool
            handler: The async function that handles tool calls
            definition: The tool schema/definition

        Returns:
            A copy of the tool definition that was registered
        """
        self.tool_handlers[name] = handler
        definition_copy = definition.copy()

        # Ensure the name in the definition matches the registered name
        definition_copy["name"] = name

        self.tool_definitions.append(definition_copy)
        logger.debug(f"Registered tool: {name}")
        return definition_copy

    def get_handler(self, name: str) -> ToolHandler:
        """Get a handler by tool name.

        Args:
            name: The name of the tool

        Returns:
            The tool handler function

        Raises:
            ValueError: If the tool is not found
        """
        if name not in self.tool_handlers:
            available_tools = ", ".join(self.tool_handlers.keys())
            raise ValueError(
                f"Tool '{name}' not found. Available tools: {available_tools}"
            )
        return self.tool_handlers[name]

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            A list of registered tool names
        """
        return list(self.tool_handlers.keys())

    def get_definitions(self) -> list[ToolSchema]:
        """Get all tool definitions for API calls.

        Returns:
            A list of tool schemas
        """
        return self.tool_definitions

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Call a tool by name with the given arguments.

        Args:
            name: The name of the tool to call
            args: The arguments to pass to the tool

        Returns:
            The result of the tool execution

        Raises:
            ValueError: If the tool is not found
        """
        handler = self.get_handler(name)
        return await handler(args)


# Registry of available system tools
_SYSTEM_TOOLS = {
    "spawn": (spawn_tool, spawn_tool_def),
    "fork": (fork_tool, fork_tool_def),
    "calculator": (calculator_tool, calculator_tool_def),
    "read_fd": (read_fd_tool, read_fd_tool_def),
    "fd_to_file": (fd_to_file_tool, fd_to_file_tool_def),
    "read_file": (read_file_tool, read_file_tool_def),
}


def get_tool(name: str) -> tuple[ToolHandler, ToolSchema]:
    """Get a tool handler and schema by name.

    Args:
        name: The name of the tool to retrieve

    Returns:
        A tuple of (handler, schema) for the requested tool

    Raises:
        ValueError: If the tool is not found
    """
    if name not in _SYSTEM_TOOLS:
        available_tools = ", ".join(_SYSTEM_TOOLS.keys())
        raise ValueError(f"Tool '{name}' not found. Available tools: {available_tools}")

    return _SYSTEM_TOOLS[name]


def list_available_tools() -> list[str]:
    """List all available system tools.

    Returns:
        A list of available tool names
    """
    return list(_SYSTEM_TOOLS.keys())


def register_system_tools(registry: ToolRegistry, process) -> None:
    """Register system tools based on enabled tools in the process.

    Args:
        registry: The ToolRegistry to register tools with
        process: The LLMProcess instance
    """
    enabled_tools = getattr(process, "enabled_tools", [])

    # Register spawn tool if enabled and process has linked programs
    if "spawn" in enabled_tools and getattr(process, "has_linked_programs", False):
        register_spawn_tool(registry, process)

    # Register fork tool if enabled
    if "fork" in enabled_tools:
        register_fork_tool(registry, process)

    # Register calculator tool if enabled
    if "calculator" in enabled_tools:
        register_calculator_tool(registry)
        
    # Register read_file tool if enabled
    if "read_file" in enabled_tools:
        register_read_file_tool(registry)
        
    # Register file descriptor tools if enabled
    if "read_fd" in enabled_tools or getattr(process, "file_descriptor_enabled", False):
        register_file_descriptor_tools(registry, process)


def register_spawn_tool(registry: ToolRegistry, process) -> None:
    """Register the spawn tool with a registry.

    Args:
        registry: The ToolRegistry to register the tool with
        process: The LLMProcess instance to bind to the tool
    """
    # Check if FD system is enabled
    fd_enabled = getattr(process, "file_descriptor_enabled", False)
    
    # Choose appropriate schema based on FD support
    if fd_enabled:
        from llmproc.tools.spawn import SPAWN_TOOL_SCHEMA_WITH_FD
        api_tool_def = SPAWN_TOOL_SCHEMA_WITH_FD.copy()
    else:
        from llmproc.tools.spawn import SPAWN_TOOL_SCHEMA_BASE
        api_tool_def = SPAWN_TOOL_SCHEMA_BASE.copy()

    # Customize description with available programs if any
    if hasattr(process, "linked_programs") and process.linked_programs:
        available_programs = ", ".join(process.linked_programs.keys())
        api_tool_def["description"] += f"\n\nAvailable programs: {available_programs}"

    # Create a handler function that binds to the process
    async def spawn_handler(args):
        # Process additional_preload_fds if FD system is enabled
        additional_preload_fds = None
        if fd_enabled:
            additional_preload_fds = args.get("additional_preload_fds")
            
        return await spawn_tool(
            program_name=args.get("program_name"),
            query=args.get("query"),
            additional_preload_files=args.get("additional_preload_files"),
            additional_preload_fds=additional_preload_fds,
            llm_process=process,
        )

    # Register with the registry
    registry.register_tool("spawn", spawn_handler, api_tool_def)

    logger.info(f"Registered spawn tool for process (with FD support: {fd_enabled})")


def register_fork_tool(registry: ToolRegistry, process) -> None:
    """Register the fork tool with a registry.

    Args:
        registry: The ToolRegistry to register the tool with
        process: The LLMProcess instance to bind to the tool
    """
    # Get tool definition
    api_tool_def = fork_tool_def.copy()

    # The actual fork implementation is handled by the process executor
    # This is just a placeholder handler for the interface
    async def fork_handler(args):
        return ToolResult.from_error(
            "Direct calls to fork_tool are not supported. This should be handled by the process executor."
        )

    # Register with the registry
    registry.register_tool("fork", fork_handler, api_tool_def)

    logger.info("Registered fork tool for process")


def register_calculator_tool(registry: ToolRegistry) -> None:
    """Register the calculator tool with a registry.

    Args:
        registry: The ToolRegistry to register the tool with
    """
    # Get tool definition
    api_tool_def = calculator_tool_def.copy()

    # Create a handler function
    async def calculator_handler(args):
        expression = args.get("expression", "")
        precision = args.get("precision", 6)
        return await calculator_tool(expression, precision)

    # Register with the registry
    registry.register_tool("calculator", calculator_handler, api_tool_def)

    logger.info("Registered calculator tool")


def register_file_descriptor_tools(registry: ToolRegistry, process) -> None:
    """Register the file descriptor tools with a registry.

    Args:
        registry: The ToolRegistry to register the tool with
        process: The LLMProcess instance to bind to the tool
    """
    # Get tool definitions
    read_fd_def = read_fd_tool_def.copy()
    fd_to_file_def = fd_to_file_tool_def.copy()

    # Create handler functions that bind to the process
    async def read_fd_handler(args):
        return await read_fd_tool(
            fd=args.get("fd"),
            page=args.get("page", 1),
            read_all=args.get("read_all", False),
            extract_to_new_fd=args.get("extract_to_new_fd", False),
            llm_process=process,
        )
        
    async def fd_to_file_handler(args):
        return await fd_to_file_tool(
            fd=args.get("fd"),
            file_path=args.get("file_path"),
            mode=args.get("mode", "write"),
            create=args.get("create", True),
            exist_ok=args.get("exist_ok", True),
            llm_process=process,
        )

    # Register with the registry
    registry.register_tool("read_fd", read_fd_handler, read_fd_def)
    
    # Register fd_to_file if it's enabled in the tools list
    if "fd_to_file" in getattr(process, "enabled_tools", []):
        registry.register_tool("fd_to_file", fd_to_file_handler, fd_to_file_def)

    # Mark that file descriptors are enabled for this process
    if not hasattr(process, "file_descriptor_enabled"):
        process.file_descriptor_enabled = True
    
    # Register tool names to prevent recursive file descriptor creation
    if hasattr(process, "fd_manager"):
        # read_fd and fd_to_file are already in the default set, but this makes it explicit
        process.fd_manager.register_fd_tool("read_fd")
        process.fd_manager.register_fd_tool("fd_to_file")

    logger.info("Registered file descriptor tools for process")


def register_read_file_tool(registry: ToolRegistry) -> None:
    """Register the read_file tool with a registry.

    Args:
        registry: The ToolRegistry to register the tool with
    """
    # Get tool definition
    api_tool_def = read_file_tool_def.copy()

    # Create a handler function
    async def read_file_handler(args):
        file_path = args.get("file_path", "")
        return await read_file_tool(file_path)

    # Register with the registry
    registry.register_tool("read_file", read_file_handler, api_tool_def)

    logger.info("Registered read_file tool")


__all__ = [
    "spawn_tool",
    "spawn_tool_def",
    "fork_tool",
    "fork_tool_def",
    "calculator_tool",
    "calculator_tool_def",
    "read_fd_tool",
    "read_fd_tool_def",
    "fd_to_file_tool",
    "fd_to_file_tool_def",
    "read_file_tool",
    "read_file_tool_def",
    "file_descriptor_instructions",
    "get_tool",
    "list_available_tools",
    "ToolSchema",
    "ToolHandler",
    "ToolRegistry",
    "register_system_tools",
    "register_spawn_tool",
    "register_fork_tool",
    "register_calculator_tool",
    "register_read_file_tool",
    "register_file_descriptor_tools",
    "ToolResult",
    "mcp",
]
