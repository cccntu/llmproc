"""LLMProgram compiler for validating and loading LLM program configurations."""

import logging
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, List, Optional, Union

import llmproc
from llmproc._program_docs import (
    ADD_LINKED_PROGRAM,
    ADD_PRELOAD_FILE,
    API_PARAMS,
    COMPILE,
    COMPILE_SELF,
    CONFIGURE_ENV_INFO,
    CONFIGURE_FILE_DESCRIPTOR,
    CONFIGURE_MCP,
    CONFIGURE_THINKING,
    ENABLE_TOKEN_EFFICIENT_TOOLS,
    INIT,
    LLMPROGRAM_CLASS,
    REGISTER_TOOLS,
    SET_TOOL_ALIASES,
)
from llmproc.env_info import EnvInfoBuilder
from llmproc.tools.builtin import BUILTIN_TOOLS
from llmproc.tools.function_tools import get_tool_name
from llmproc.tools.mcp import MCPTool


def convert_to_callables(tools: list[Union[str, Callable, MCPTool]]) -> list[Callable]:
    """Convert string tool names to callable functions.

    Args:
        tools: List of string names, callable functions, or MCPTool objects

    Returns:
        List of callable functions, filtering out MCPTool objects

    Raises:
        ValueError: If an item in the list is not a string, callable, or MCPTool,
                   or if a string doesn't correspond to a builtin tool
    """
    # Ensure tools is a list
    if not isinstance(tools, list):
        tools = [tools]

    result = []
    for tool in tools:
        if isinstance(tool, str):
            if tool in BUILTIN_TOOLS:
                result.append(BUILTIN_TOOLS[tool])
            else:
                raise ValueError(f"Unknown tool name: '{tool}'")
        elif callable(tool):
            result.append(tool)
        elif isinstance(tool, MCPTool):
            # MCPTool objects are handled separately in __init__
            pass
        else:
            raise ValueError(f"Expected string, callable, or MCPTool, got {type(tool)}")
    return result


# Set up logger
logger = logging.getLogger(__name__)


# Global singleton registry for compiled programs
class ProgramRegistry:
    """Global registry for compiled programs to avoid duplicate compilation."""

    _instance = None

    def __new__(cls):
        """Create a singleton instance of ProgramRegistry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._compiled_programs = {}
        return cls._instance

    def register(self, path: Path, program: "LLMProgram") -> None:
        """Register a compiled program."""
        self._compiled_programs[str(path.resolve())] = program

    def get(self, path: Path) -> Optional["LLMProgram"]:
        """Get a compiled program if it exists."""
        return self._compiled_programs.get(str(path.resolve()))

    def contains(self, path: Path) -> bool:
        """Check if a program has been compiled."""
        return str(path.resolve()) in self._compiled_programs

    def clear(self) -> None:
        """Clear all compiled programs (mainly for testing)."""
        self._compiled_programs.clear()


class LLMProgram:
    """Program definition for LLM processes."""

    def __init__(
        self,
        model_name: str,
        provider: str,
        system_prompt: str = None,
        system_prompt_file: str = None,
        parameters: dict[str, Any] = None,
        display_name: str | None = None,
        preload_files: list[str] | None = None,
        mcp_config_path: str | None = None,
        tools: list[Any] = None,
        tool_aliases: dict[str, str] = None,
        linked_programs: dict[str, Union[str, "LLMProgram"]] | None = None,
        linked_program_descriptions: dict[str, str] | None = None,
        env_info: dict[str, Any] | None = None,
        file_descriptor: dict[str, Any] | None = None,
        base_dir: Path | None = None,
        disable_automatic_caching: bool = False,
        project_id: str | None = None,
        region: str | None = None,
        user_prompt: str = None,
        max_iterations: int = 10,
    ):
        """Initialize a program."""
        # Flag to track if this program has been fully compiled
        self.compiled = False
        self._system_prompt_file = system_prompt_file

        # Handle system prompt (either direct or from file)
        if system_prompt and system_prompt_file:
            raise ValueError("Cannot specify both system_prompt and system_prompt_file")

        # Initialize core attributes
        self.model_name = model_name
        self.provider = provider
        self.system_prompt = system_prompt
        self.project_id = project_id
        self.region = region
        self.parameters = parameters or {}
        self.display_name = display_name or f"{provider.title()} {model_name}"
        self.preload_files = preload_files or []
        self.mcp_config_path = mcp_config_path
        self.disable_automatic_caching = disable_automatic_caching
        self.user_prompt = user_prompt
        self.max_iterations = max_iterations

        # Initialize the tool manager
        from llmproc.tools import ToolManager

        self.tool_manager = ToolManager()

        # Process tools parameter: can include str names, callables, or MCPTool descriptors
        if tools:
            # Normalize to list
            raw_tools = tools if isinstance(tools, list) else [tools]

            # Register all tools with the tool manager
            self.register_tools(raw_tools)

        # Process aliases separately if provided
        if tool_aliases:
            self.set_tool_aliases(tool_aliases)

        self.linked_programs = linked_programs or {}
        self.linked_program_descriptions = linked_program_descriptions or {}
        self.env_info = env_info or {
            "variables": []
        }  # Default to empty list (disabled)
        self.file_descriptor = file_descriptor or {}
        self.base_dir = base_dir

    def _validate_tool_dependencies(self) -> None:
        """Validate tool dependencies are satisfied.

        This method performs explicit validation of tool dependencies during compilation,
        ensuring that necessary requirements for tools are met before attempting to use them.

        Validates:
        1. Spawn tool requires linked programs
        2. FD tools require file descriptor system

        Raises:
            ValueError: If dependencies for enabled tools are not satisfied
        """
        registered_tools = self.tool_manager.get_registered_tools()

        # Linked programs dependency for spawn
        if "spawn" in registered_tools:
            has_linked_programs = hasattr(self, "linked_programs") and bool(self.linked_programs)
            if not has_linked_programs:
                raise ValueError("Tool 'spawn' requires linked programs, but none are configured")

        # File descriptor dependency for fd tools
        if any(name in registered_tools for name in ["read_fd", "fd_to_file"]):
            fd_enabled = (
                hasattr(self, "file_descriptor")
                and isinstance(self.file_descriptor, dict)
                and self.file_descriptor.get("enabled", False)
            )
            if not fd_enabled:
                raise ValueError("Tools 'read_fd' or 'fd_to_file' require file descriptor system, but it's not enabled")

    def _compile_self(self) -> "LLMProgram":
        """Internal method to validate and compile this program."""
        # Skip if already compiled
        if self.compiled:
            return self

        # Resolve system prompt from file if specified
        if self._system_prompt_file and not self.system_prompt:
            try:
                with open(self._system_prompt_file) as f:
                    self.system_prompt = f.read()
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"System prompt file not found: {self._system_prompt_file}"
                )

        # Default system_prompt to empty string if None
        if self.system_prompt is None:
            self.system_prompt = ""
            
        # Validate required fields
        if not self.model_name or not self.provider:
            missing = []
            if not self.model_name:
                missing.append("model_name")
            if not self.provider:
                missing.append("provider")
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        # Tool management is now handled directly by the ToolManager
        # Process function tools to ensure they're properly prepared for registration
        self.tool_manager.process_function_tools()

        # Resolve File Descriptor and Tools dependencies
        self._resolve_fd_tool_dependencies()

        # Validate tool dependencies explicitly during compilation
        self._validate_tool_dependencies()

        # Handle linked programs recursively
        self._compile_linked_programs()

        # Mark as compiled
        self.compiled = True
        return self

    def _resolve_fd_tool_dependencies(self) -> None:
        """Resolve dependencies between file descriptor system and FD tools.

        This method ensures consistency between:
        1. File descriptor system configuration (self.file_descriptor)
        2. Enabled tools that interact with file descriptors (read_fd, fd_to_file)

        The rules are:
        - If FD system is enabled, ensure read_fd tool is available
        - If FD tools are enabled but FD system isn't, enable the FD system
        """
        from llmproc.file_descriptors.constants import FD_RELATED_TOOLS

        # Get current state
        has_fd_config = hasattr(self, "file_descriptor") and isinstance(
            self.file_descriptor, dict
        )
        fd_enabled = has_fd_config and self.file_descriptor.get("enabled", False)
        registered_tools = self.tool_manager.get_registered_tools()
        has_fd_tools = any(tool in FD_RELATED_TOOLS for tool in registered_tools)

        if fd_enabled and not has_fd_tools:
            # If FD system is enabled but no FD tools, add read_fd
            if "read_fd" not in registered_tools:
                # Convert to callable and add to enabled tools
                read_fd_callable = BUILTIN_TOOLS["read_fd"]
                current_tools = self.tool_manager.function_tools.copy()
                self.register_tools(current_tools + [read_fd_callable])
                logger.info("File descriptor system enabled, automatically adding read_fd tool")

        elif has_fd_tools and not fd_enabled:
            # If FD tools are enabled but FD system isn't, enable the FD system
            if not has_fd_config:
                self.file_descriptor = {"enabled": True}
            else:
                self.file_descriptor["enabled"] = True
            logger.info("FD tools enabled, automatically enabling file descriptor system")

    def _compile_linked_programs(self) -> None:
        """Compile linked programs recursively."""
        compiled_linked = {}

        # Process each linked program
        for name, program_or_path in self.linked_programs.items():
            if isinstance(program_or_path, str):
                # It's a path, load and compile using from_toml
                try:
                    linked_program = LLMProgram.from_toml(program_or_path)
                    compiled_linked[name] = linked_program
                except FileNotFoundError:
                    warnings.warn(
                        f"Linked program not found: {program_or_path}", stacklevel=2
                    )
            elif isinstance(program_or_path, LLMProgram):
                # It's already a program instance, compile it if not already compiled
                if not program_or_path.compiled:
                    program_or_path._compile_self()
                compiled_linked[name] = program_or_path
            else:
                raise ValueError(
                    f"Invalid linked program type for {name}: {type(program_or_path)}"
                )

        # Replace linked_programs with compiled versions
        self.linked_programs = compiled_linked

    def add_linked_program(
        self, name: str, program: "LLMProgram", description: str = ""
    ) -> "LLMProgram":
        """Link another program to this one."""
        self.linked_programs[name] = program
        self.linked_program_descriptions[name] = description
        return self

    def add_preload_file(self, file_path: str) -> "LLMProgram":
        """Add a file to preload into the system prompt."""
        self.preload_files.append(file_path)
        return self

    def configure_env_info(self, variables: list[str] | str = "all") -> "LLMProgram":
        """Configure environment information sharing."""
        if variables == "all":
            self.env_info = {"variables": "all"}
        else:
            self.env_info = {"variables": variables}
        return self

    def configure_file_descriptor(
        self,
        enabled: bool = True,
        max_direct_output_chars: int = 8000,
        default_page_size: int = 4000,
        max_input_chars: int = 8000,
        page_user_input: bool = True,
        enable_references: bool = True,
    ) -> "LLMProgram":
        """Configure the file descriptor system."""
        self.file_descriptor = {
            "enabled": enabled,
            "max_direct_output_chars": max_direct_output_chars,
            "default_page_size": default_page_size,
            "max_input_chars": max_input_chars,
            "page_user_input": page_user_input,
            "enable_references": enable_references,
        }
        return self

    def configure_thinking(
        self, enabled: bool = True, budget_tokens: int = 4096
    ) -> "LLMProgram":
        """Configure Claude 3.7 thinking capability."""
        # Ensure parameters dict exists
        if self.parameters is None:
            self.parameters = {}

        # Configure thinking
        self.parameters["thinking"] = {
            "type": "enabled" if enabled else "disabled",
            "budget_tokens": budget_tokens,
        }
        return self

    def enable_token_efficient_tools(self) -> "LLMProgram":
        """Enable token-efficient tool use for Claude 3.7 models."""
        # Ensure parameters dict exists
        if self.parameters is None:
            self.parameters = {}

        # Ensure extra_headers dict exists
        if "extra_headers" not in self.parameters:
            self.parameters["extra_headers"] = {}

        # Add header for token-efficient tools
        self.parameters["extra_headers"]["anthropic-beta"] = (
            "token-efficient-tools-2025-02-19"
        )
        return self

    def register_tools(self, tools: list[Union[str, Callable, MCPTool]]) -> "LLMProgram":
        """Register tools for use in the program.

        This method accepts string names, callable functions, and MCPTool objects,
        providing a consistent interface with the constructor.

        Args:
            tools: List of string names, callable functions, or MCPTool objects

        Returns:
            self (for method chaining)

        Raises:
            ValueError: If a string name doesn't correspond to a builtin tool,
                       or if an item is not a valid tool type
        """
        if not isinstance(tools, list):
            tools = [tools]

        # Split tools into MCPTool descriptors and other tools
        mcp_tools = []
        other_tools = []

        for tool in tools:
            if isinstance(tool, MCPTool):
                mcp_tools.append(tool)
            else:
                other_tools.append(tool)

        # Convert string names to callables for consistent handling
        if other_tools:
            callables = convert_to_callables(other_tools)
            # Delegate to the tool manager
            self.tool_manager.register_tools(callables)

        # Register MCPTool descriptors separately
        if mcp_tools:
            self.tool_manager.register_tools(mcp_tools)

        return self

    def get_registered_tools(self) -> list[str]:
        """Get the list of registered tool names.

        Returns:
            A list of the currently registered tool names

        Note:
            This method delegates to the tool_manager, which is the
            single source of truth for registered tools.
        """
        return self.tool_manager.get_registered_tools()

    def set_enabled_tools(self, tools: list[Union[str, Callable]]) -> "LLMProgram":
        """Alias for register_tools for backward compatibility."""
        return self.register_tools(tools)

    def set_tool_aliases(self, aliases: dict[str, str]) -> "LLMProgram":
        """Set tool aliases, merging with any existing aliases."""
        # Validate aliases is a dictionary
        if not isinstance(aliases, dict):
            raise ValueError(f"Expected dictionary of aliases, got {type(aliases)}")

        # Check for one-to-one mapping (no multiple aliases to same target)
        targets = {}
        for alias, target in aliases.items():
            if target in targets:
                raise ValueError(
                    f"Multiple aliases point to the same target tool '{target}': '{targets[target]}' and '{alias}'. One-to-one mapping is required."
                )
            targets[target] = alias

        # Register aliases with the tool manager
        self.tool_manager.register_aliases(aliases)

        return self

    def set_user_prompt(self, prompt: str) -> "LLMProgram":
        """Set a user prompt to be executed automatically when the program starts."""
        self.user_prompt = prompt
        return self

    def set_max_iterations(self, max_iterations: int) -> "LLMProgram":
        """Set the default maximum number of iterations for this program."""
        if max_iterations <= 0:
            raise ValueError("max_iterations must be a positive integer")
        self.max_iterations = max_iterations
        return self

    def configure_mcp(self, config_path: str) -> "LLMProgram":
        """Configure Model Context Protocol (MCP) server connection."""
        self.mcp_config_path = config_path
        return self

    def compile(self) -> "LLMProgram":
        """Validate and compile this program."""
        # Call the internal _compile_self method
        return self._compile_self()

    @property
    def api_params(self) -> dict[str, Any]:
        """Get API parameters for LLM API calls."""
        return self.parameters.copy() if self.parameters else {}

    @classmethod
    def from_toml(cls, toml_file, **kwargs):
        """Create a program from a TOML file.

        This method delegates to ProgramLoader.from_toml for backward compatibility.

        Args:
            toml_file: Path to the TOML file
            **kwargs: Additional parameters to override TOML values

        Returns:
            An initialized LLMProgram instance
        """
        from llmproc.config.program_loader import ProgramLoader

        return ProgramLoader.from_toml(toml_file, **kwargs)

    def get_tool_configuration(self, linked_programs_instances: dict[str, Any] | None = None) -> dict:
        """Create tool configuration dictionary for initialization.

        This method extracts the necessary components from the program to initialize
        tools without requiring a process instance, avoiding circular dependencies.

        Args:
            linked_programs_instances: Dictionary of pre-initialized LLMProcess instances

        Returns:
            Dictionary with tool configuration components
        """
        # Ensure the program is compiled
        if not self.compiled:
            self.compile()

        # Extract core configuration properties
        config = {
            "provider": self.provider,
            "mcp_config_path": getattr(self, "mcp_config_path", None),
            "mcp_enabled": getattr(self, "mcp_config_path", None) is not None,
        }

        # Handle linked programs
        linked_programs = {}
        if linked_programs_instances:
            linked_programs = linked_programs_instances
            config["has_linked_programs"] = bool(linked_programs)
        elif hasattr(self, "linked_programs") and self.linked_programs:
            linked_programs = self.linked_programs
            config["has_linked_programs"] = True
        else:
            config["has_linked_programs"] = False

        config["linked_programs"] = linked_programs

        # Add linked program descriptions if available
        if (
            hasattr(self, "linked_program_descriptions")
            and self.linked_program_descriptions
        ):
            config["linked_program_descriptions"] = self.linked_program_descriptions
        else:
            config["linked_program_descriptions"] = {}

        # Create file descriptor manager if needed
        fd_manager = None
        if hasattr(self, "file_descriptor"):
            fd_config = self.file_descriptor
            enabled = fd_config.get("enabled", False)

            if enabled:
                # Get configuration values with defaults
                default_page_size = fd_config.get("default_page_size", 4000)
                max_direct_output_chars = fd_config.get("max_direct_output_chars", 8000)
                max_input_chars = fd_config.get("max_input_chars", 8000)
                page_user_input = fd_config.get("page_user_input", True)
                enable_references = fd_config.get("enable_references", False)

                # Create fd_manager
                from llmproc.file_descriptors.manager import FileDescriptorManager

                fd_manager = FileDescriptorManager(
                    default_page_size=default_page_size,
                    max_direct_output_chars=max_direct_output_chars,
                    max_input_chars=max_input_chars,
                    page_user_input=page_user_input,
                    enable_references=enable_references,
                )

                config["references_enabled"] = enable_references

        config["fd_manager"] = fd_manager
        config["file_descriptor_enabled"] = fd_manager is not None

        logger.info("Created tool configuration for initialization")
        return config

    async def start(self) -> "LLMProcess":  # noqa: F821
        """Create and fully initialize an LLMProcess from this program.

        ✅ THIS IS THE CORRECT WAY TO CREATE AN LLMPROCESS ✅

        ```python
        program = LLMProgram.from_toml("config.toml")
        process = await program.start()  # Correct initialization pattern
        ```

        This method delegates the entire program-to-process creation logic
        to the `llmproc.program_exec.create_process` function, which handles
        compilation, tool initialization, process instantiation, and runtime
        context setup in a modular way.

        ⚠️ IMPORTANT: Never use direct constructor `LLMProcess(program=...)` ⚠️
        Direct instantiation will result in broken context-aware tools (spawn, goto, fd_tools, etc.)
        and bypass the proper tool initialization sequence.

        Returns:
            A fully initialized LLMProcess ready for execution with properly configured tools
        """
        # Delegate to the modular implementation in program_exec.py
        from llmproc.program_exec import create_process

        return await create_process(self)


# Apply full docstrings to class and methods
LLMProgram.__doc__ = LLMPROGRAM_CLASS
LLMProgram.__init__.__doc__ = INIT
LLMProgram._compile_self.__doc__ = COMPILE_SELF
LLMProgram.add_linked_program.__doc__ = ADD_LINKED_PROGRAM
LLMProgram.add_preload_file.__doc__ = ADD_PRELOAD_FILE
LLMProgram.configure_env_info.__doc__ = CONFIGURE_ENV_INFO
LLMProgram.configure_file_descriptor.__doc__ = CONFIGURE_FILE_DESCRIPTOR
LLMProgram.configure_thinking.__doc__ = CONFIGURE_THINKING
LLMProgram.enable_token_efficient_tools.__doc__ = ENABLE_TOKEN_EFFICIENT_TOOLS
LLMProgram.register_tools.__doc__ = REGISTER_TOOLS
LLMProgram.set_tool_aliases.__doc__ = SET_TOOL_ALIASES
LLMProgram.configure_mcp.__doc__ = CONFIGURE_MCP
LLMProgram.compile.__doc__ = COMPILE
LLMProgram.api_params.__doc__ = API_PARAMS
