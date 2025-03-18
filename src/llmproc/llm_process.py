"""LLMProcess class for handling LLM interactions."""

import asyncio
import logging
import os
import warnings
from pathlib import Path
from typing import Any, TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from llmproc.program import LLMProgram

try:
    from mcp_registry import MCPAggregator, ServerRegistry, get_config_path

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

from llmproc.providers import get_provider_client
from llmproc.providers.anthropic_process_executor import AnthropicProcessExecutor
from llmproc.tools import ToolRegistry, register_system_tools, mcp

load_dotenv()

# Set up logger
logger = logging.getLogger(__name__)


class LLMProcess:
    """Process for interacting with LLMs using standardized program definitions."""

    def __init__(
        self,
        program: "LLMProgram",
        linked_programs_instances: dict[str, "LLMProcess"] | None = None,
    ) -> None:
        """Initialize LLMProcess from a compiled program.

        Args:
            program: A compiled LLMProgram instance
            linked_programs_instances: Dictionary of pre-initialized LLMProcess instances

        Raises:
            NotImplementedError: If the provider is not implemented
            ImportError: If the required package for a provider is not installed
            FileNotFoundError: If required files (system prompt file, MCP config file) cannot be found
            ValueError: If MCP is enabled but provider is not anthropic

        Notes:
            Missing preload files will generate warnings but won't cause the initialization to fail
            For async initialization (MCP), use the create() factory method instead.
        """
        # Store the program reference
        self.program = program

        # Extract core attributes from program
        self.model_name = program.model_name
        self.provider = program.provider
        self.system_prompt = program.system_prompt  # Basic system prompt without enhancements
        self.display_name = program.display_name
        self.base_dir = program.base_dir
        self.config_dir = self.base_dir  # Alias for backward compatibility
        self.api_params = program.api_params
        self.parameters = {} # Keep empty - parameters are already processed in program

        # Initialize state for preloaded content
        self.preloaded_content = {}

        # Track the enriched system prompt (will be set on first run)
        self.enriched_system_prompt = None

        # Extract tool configuration
        self.enabled_tools = []
        if hasattr(program, 'tools') and program.tools:
            # Get enabled tools from the program
            self.enabled_tools = program.tools.get("enabled", [])

        # Initialize the tool registry
        self.tool_registry = ToolRegistry()

        # MCP Configuration
        self.mcp_enabled = False
        self.mcp_config_path = getattr(program, "mcp_config_path", None)
        self.mcp_tools = getattr(program, "mcp_tools", {})
        self._mcp_initialized = False
        
        # Mark if we need async initialization
        self._needs_async_init = (self.mcp_config_path is not None and bool(self.mcp_tools))

        # Linked Programs Configuration
        self.linked_programs = {}
        self.has_linked_programs = False

        # Initialize linked programs if provided in constructor
        if linked_programs_instances:
            self.has_linked_programs = True
            self.linked_programs = linked_programs_instances
        # Otherwise use linked programs from the program - store as program objects
        elif hasattr(program, "linked_programs") and program.linked_programs:
            self.has_linked_programs = True
            self.linked_programs = program.linked_programs

        # Initialize system tools 
        self._initialize_tools()

        # Get project_id and region for Vertex if provided in parameters
        project_id = getattr(program, "project_id", None)
        region = getattr(program, "region", None)

        # Initialize the client
        self.client = get_provider_client(self.provider, self.model_name, project_id, region)

        # Store the original system prompt before any files are preloaded
        self.original_system_prompt = self.system_prompt

        # Initialize message state (will set system message on first run)
        self.state = []

        # Preload files if specified
        if hasattr(program, "preload_files") and program.preload_files:
            self.preload_files(program.preload_files)
            
    @classmethod
    async def create(
        cls, 
        program: "LLMProgram",
        linked_programs_instances: dict[str, "LLMProcess"] | None = None,
    ) -> "LLMProcess":
        """Create and fully initialize an LLMProcess asynchronously.
        
        This factory method handles async initialization in a clean way,
        ensuring the instance is fully ready to use when returned.
        
        Args:
            program: The LLMProgram to use
            linked_programs_instances: Dictionary of pre-initialized LLMProcess instances
            
        Returns:
            A fully initialized LLMProcess
            
        Raises:
            All exceptions from __init__, plus:
            RuntimeError: If MCP initialization fails
        """
        # Create instance with basic initialization
        instance = cls(program, linked_programs_instances)
        
        # Perform async initialization if needed
        if instance._needs_async_init:
            instance.mcp_enabled = True
            await instance._initialize_mcp_tools()
        
        return instance

    def preload_files(self, file_paths: list[str]) -> None:
        """Preload files and add their content to the preloaded_content dictionary.

        This method loads file content into memory but does not modify the state.
        The enriched system prompt with preloaded content will be generated on first run.
        Missing files will generate warnings but won't cause errors.

        Args:
            file_paths: List of file paths to preload
        """
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                # Issue a clear warning with both specified and resolved paths
                warnings.warn(f"Preload file not found - Specified: '{file_path}', Resolved: '{os.path.abspath(file_path)}'")
                continue

            content = path.read_text()
            self.preloaded_content[str(path)] = content

        # Reset the enriched system prompt if it was already generated
        # so it will be regenerated with the new preloaded content
        if self.enriched_system_prompt is not None:
            self.enriched_system_prompt = None

    @classmethod
    def from_toml(cls, toml_path: str | Path) -> "LLMProcess":
        """Create an LLMProcess from a TOML program file.

        This method compiles the main program and all linked programs recursively,
        then instantiates an LLMProcess with access to all linked programs as Program objects.
        Linked programs are only compiled, not instantiated as processes, until they are needed.
        
        Note: This is a synchronous method. If your program requires async initialization
        (e.g., MCP tools), you should use the async version from_toml_async instead.

        Args:
            toml_path: Path to the TOML program file

        Returns:
            An initialized LLMProcess instance with access to linked programs

        Raises:
            ValueError: If program configuration is invalid
            FileNotFoundError: If the TOML file cannot be found
        """
        # Import the compiler
        from llmproc.program import LLMProgram

        # Compile the main program and all linked programs
        # This will create a properly linked object graph with Program objects
        main_path = Path(toml_path).resolve()
        main_program = LLMProgram.compile(main_path, include_linked=True, check_linked_files=True)

        if not main_program:
            raise ValueError(f"Failed to compile program from {toml_path}")

        # Create the main process
        main_process = cls(program=main_program)

        # The linked_programs attribute of main_program should now contain references to
        # compiled Program objects instead of path strings
        if hasattr(main_program, 'linked_programs') and main_program.linked_programs:
            main_process.has_linked_programs = bool(main_program.linked_programs)

        return main_process
        
    @classmethod
    async def from_toml_async(cls, toml_path: str | Path) -> "LLMProcess":
        """Create an LLMProcess from a TOML program file with async initialization.

        This method compiles the main program and all linked programs recursively,
        then instantiates an LLMProcess with async initialization for MCP and other
        features that require async setup.

        Args:
            toml_path: Path to the TOML program file

        Returns:
            A fully initialized LLMProcess instance with access to linked programs

        Raises:
            ValueError: If program configuration is invalid
            FileNotFoundError: If the TOML file cannot be found
            RuntimeError: If async initialization fails
        """
        # Import the compiler
        from llmproc.program import LLMProgram

        # Compile the main program and all linked programs
        main_path = Path(toml_path).resolve()
        main_program = LLMProgram.compile(main_path, include_linked=True, check_linked_files=True)

        if not main_program:
            raise ValueError(f"Failed to compile program from {toml_path}")

        # Create the main process with async initialization
        main_process = await cls.create(program=main_program)

        return main_process


    async def run(self, user_input: str, max_iterations: int = 10) -> int:
        """Run the LLM process with user input asynchronously.

        This method supports full tool execution with proper async handling.
        If used in a synchronous context, it will automatically run in a new event loop.

        Args:
            user_input: The user message to process
            max_iterations: Maximum number of tool-calling iterations

        Returns:
            The number of API calls used during processing
        """
        # Check if we're in an event loop
        try:
            asyncio.get_running_loop()
            in_event_loop = True
        except RuntimeError:
            in_event_loop = False

        # If not in an event loop, run in a new one
        if not in_event_loop:
            return asyncio.run(self._async_run(user_input, max_iterations))
        else:
            return await self._async_run(user_input, max_iterations)

    async def _async_run(self, user_input: str, max_iterations: int = 10) -> int:
        """Internal async implementation of run.

        Args:
            user_input: The user message to process
            max_iterations: Maximum number of tool-calling iterations

        Returns:
            The number of API calls used during processing

        Raises:
            ValueError: If user_input is empty
        """
        # Verify user input isn't empty
        if not user_input or user_input.strip() == "":
            raise ValueError("User input cannot be empty")
            
        # Initialize MCP tools if needed and not already initialized
        if self._needs_async_init and not self._mcp_initialized:
            self.mcp_enabled = True
            await self._initialize_mcp_tools()

        # Generate enriched system prompt on first run
        if self.enriched_system_prompt is None:
            self.enriched_system_prompt = self.program.get_enriched_system_prompt(
                process_instance=self,
                include_env=True
            )
            # Set the system message with enriched prompt
            self.state = [{"role": "system", "content": self.enriched_system_prompt}]

        # Add user input to state
        self.state.append({"role": "user", "content": user_input})

        # Keep messages as an alias to state for compatibility
        self.messages = self.state

        # Create provider-specific process executors
        if self.provider == "openai":
            raise NotImplementedError("OpenAI is not yet implemented")
        elif self.provider == "anthropic":
            # Use the stateless AnthropicProcessExecutor
            executor = AnthropicProcessExecutor()
            return await executor.run(self, user_input, max_iterations)
        elif self.provider == "vertex":
            raise NotImplementedError("Vertex is not yet implemented")
        else:
            raise NotImplementedError(f"Provider {self.provider} not implemented")

    def get_state(self) -> list[dict[str, str]]:
        """Return the current conversation state.

        Returns:
            A copy of the current conversation state
        """
        return self.state.copy()

    async def _initialize_mcp_tools(self) -> None:
        """Initialize MCP registry and tools.

        This sets up the MCP registry and filters tools based on user configuration.
        Only tools explicitly specified in the mcp_tools configuration will be enabled.
        Only servers that have tools configured will be initialized.
        """
        if not self.mcp_enabled:
            return

        success = await mcp.initialize_mcp_tools(
            self,
            self.tool_registry,
            self.mcp_config_path,
            self.mcp_tools
        )
        
        if not success:
            logger.warning("Failed to initialize MCP tools. Some features may not work correctly.")


    def reset_state(
        self, keep_system_prompt: bool = True, keep_preloaded: bool = True
    ) -> None:
        """Reset the conversation state.

        Args:
            keep_system_prompt: Whether to keep the system prompt in the state
            keep_preloaded: Whether to keep preloaded file content in the state
        """
        # Clear the state
        self.state = []

        # Handle preloaded content
        if not keep_preloaded:
            # Clear preloaded content
            self.preloaded_content = {}

        # Always reset the enriched system prompt - it will be regenerated on next run
        # with the correct combination of system prompt and preloaded content
        self.enriched_system_prompt = None

    def _initialize_tools(self) -> None:
        """Initialize all system tools.

        MCP tools require async initialization and are handled separately
        via the create() factory method or lazy initialization in run().
        """
        # Validate MCP configuration if present
        if self._needs_async_init:
            if not HAS_MCP:
                raise ImportError(
                    "MCP features require the mcp-registry package. Install it with 'pip install mcp-registry'."
                )

            # Currently only support Anthropic with MCP
            if self.provider != "anthropic":
                raise ValueError(
                    "MCP features are currently only supported with the Anthropic provider"
                )

        # Register system tools using the ToolRegistry
        register_system_tools(self.tool_registry, self)

    @property
    def tools(self) -> list:
        """Property to access tool definitions.
        
        Returns:
            List of tool definitions.
        """
        return self.tool_registry.get_definitions()
        
    @property
    def tool_handlers(self) -> dict:
        """Property to access tool handlers.
        
        Returns:
            Dictionary of tool handlers.
        """
        return self.tool_registry.tool_handlers
    
    async def call_tool(self, tool_name: str, args: dict) -> Any:
        """Call a tool by name with the given arguments.

        This method provides a unified interface for calling any registered tool,
        whether it's an MCP tool or a system tool like spawn or fork.

        Args:
            tool_name: The name of the tool to call
            args: The arguments to pass to the tool

        Returns:
            The result of the tool execution

        Raises:
            ValueError: If the tool is not found
            RuntimeError: If the tool execution fails
        """
        try:
            return await self.tool_registry.call_tool(tool_name, args)
        except Exception as e:
            raise RuntimeError(f"Error executing tool '{tool_name}': {str(e)}")

    def get_last_message(self) -> str:
        """Get the most recent message from the conversation.

        Returns:
            The text content of the last assistant message, 
            or an empty string if the last message is not from an assistant.
            
        Note:
            This handles both string content and structured content blocks from
            providers like Anthropic.
        """
        # Check if state has any messages
        if not self.state:
            return ""
            
        # Get the last message
        last_message = self.state[-1]
        
        # Return content if it's an assistant message, empty string otherwise
        if last_message.get("role") == "assistant" and "content" in last_message:
            content = last_message["content"]
            
            # If content is a string, return it directly
            if isinstance(content, str):
                return content
                
            # Handle Anthropic's content blocks format
            if isinstance(content, list):
                extracted_text = []
                for block in content:
                    # Handle text blocks
                    if isinstance(block, dict) and block.get("type") == "text":
                        extracted_text.append(block.get("text", ""))
                    # Handle TextBlock objects which may be used by Anthropic
                    elif hasattr(block, "text") and hasattr(block, "type"):
                        if getattr(block, "type") == "text":
                            extracted_text.append(getattr(block, "text", ""))
                
                return " ".join(extracted_text)
        
        return ""

    async def fork_process(self) -> "LLMProcess":
        """Create a deep copy of this process with preserved state.

        This implements the fork system call semantics where a copy of the
        process is created with the same state and configuration. The forked
        process is completely independent and can run separate tasks.

        Returns:
            A new LLMProcess instance that is a deep copy of this one
        """
        import copy

        # Create a new instance of LLMProcess with the same program
        forked_process = LLMProcess(program=self.program)

        # Copy the enriched system prompt if it exists
        if hasattr(self, 'enriched_system_prompt') and self.enriched_system_prompt:
            forked_process.enriched_system_prompt = self.enriched_system_prompt

        # Deep copy the conversation state
        forked_process.state = copy.deepcopy(self.state)

        # Copy any preloaded content
        if hasattr(self, 'preloaded_content') and self.preloaded_content:
            forked_process.preloaded_content = copy.deepcopy(self.preloaded_content)

        # No need to copy tools and tool_handlers - they are properties now
        
        # If the parent process had MCP initialized, replicate the state in the fork
        if self.mcp_enabled and self._mcp_initialized:
            forked_process.mcp_enabled = True
            forked_process._mcp_initialized = True
            
            # Copy the aggregator if it exists
            if hasattr(self, 'aggregator'):
                forked_process.aggregator = self.aggregator

        # Preserve any other state we need
        # Note: We don't copy tool handlers as they're already set up in the constructor

        return forked_process
