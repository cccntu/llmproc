"""LLMProgram compiler for validating and loading LLM program configurations."""

import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
from collections import deque

import tomllib
from pydantic import BaseModel, Field, RootModel, ValidationError, field_validator, model_validator


# Global singleton registry for compiled programs
class ProgramRegistry:
    """Global registry for compiled programs to avoid duplicate compilation."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProgramRegistry, cls).__new__(cls)
            cls._instance._compiled_programs = {}
        return cls._instance
    
    def register(self, path: Path, program: 'LLMProgram') -> None:
        """Register a compiled program."""
        self._compiled_programs[str(path.resolve())] = program
        
    def get(self, path: Path) -> Optional['LLMProgram']:
        """Get a compiled program if it exists."""
        return self._compiled_programs.get(str(path.resolve()))
        
    def contains(self, path: Path) -> bool:
        """Check if a program has been compiled."""
        return str(path.resolve()) in self._compiled_programs
        
    def clear(self) -> None:
        """Clear all compiled programs (mainly for testing)."""
        self._compiled_programs.clear()


# Pydantic models for program validation
class ModelConfig(BaseModel):
    """Model configuration section."""
    name: str
    provider: str
    display_name: Optional[str] = None

    @field_validator('provider')
    def validate_provider(cls, v):
        """Validate that the provider is supported."""
        supported_providers = {'openai', 'anthropic', 'vertex'}
        if v not in supported_providers:
            raise ValueError(f"Provider '{v}' not supported. Must be one of: {', '.join(supported_providers)}")
        return v


class PromptConfig(BaseModel):
    """Prompt configuration section."""
    system_prompt: Optional[str] = ""
    system_prompt_file: Optional[str] = None

    @model_validator(mode='after')
    def check_prompt_sources(self):
        """Check that at least one prompt source is provided."""
        if not self.system_prompt and not self.system_prompt_file:
            # Set default empty system prompt
            self.system_prompt = ""
        
        return self
        
    def resolve(self, base_dir: Optional[Path] = None) -> str:
        """Resolve the system prompt, loading from file if specified.
        
        Args:
            base_dir: Base directory for resolving relative file paths
            
        Returns:
            Resolved system prompt string
            
        Raises:
            FileNotFoundError: If system_prompt_file is specified but doesn't exist
        """
        # First check for system_prompt_file (takes precedence)
        if self.system_prompt_file:
            # Determine file path, using base_dir for relative paths if provided
            file_path = Path(self.system_prompt_file)
            if not file_path.is_absolute() and base_dir:
                file_path = base_dir / file_path
                
            if file_path.exists():
                return file_path.read_text()
            else:
                raise FileNotFoundError(f"System prompt file not found - Specified: '{self.system_prompt_file}', Resolved: '{file_path}'")
                
        # Return system_prompt (or empty string if neither is specified)
        return self.system_prompt or ""


class PreloadConfig(BaseModel):
    """Preload configuration section."""
    files: List[str] = []


class MCPToolsConfig(RootModel):
    """MCP tools configuration."""
    root: Dict[str, Union[List[str], str]] = {}

    @field_validator('root')
    def validate_tools(cls, v):
        """Validate that tool configurations are either lists or 'all'."""
        for server, tools in v.items():
            if not isinstance(tools, list) and tools != "all":
                raise ValueError(f"Tool configuration for server '{server}' must be 'all' or a list of tool names")
        return v


class MCPConfig(BaseModel):
    """MCP configuration section."""
    config_path: Optional[str] = None
    tools: Optional[MCPToolsConfig] = None


class ToolsConfig(BaseModel):
    """Tools configuration section."""
    enabled: List[str] = []


class EnvInfoConfig(BaseModel):
    """Environment information configuration section."""
    variables: Union[List[str], str] = []  # Empty list by default (disabled)
    # Allow additional custom environment variables as strings
    model_config = {
        "extra": "allow"
    }


class DebugConfig(BaseModel):
    """Debug configuration section."""
    debug_tools: bool = False


class LinkedProgramsConfig(RootModel):
    """Linked programs configuration section."""
    root: Dict[str, str] = {}


class LLMProgramConfig(BaseModel):
    """Full LLM program configuration."""
    model: ModelConfig
    prompt: PromptConfig = PromptConfig()
    parameters: Dict[str, Any] = {}
    preload: Optional[PreloadConfig] = PreloadConfig()
    mcp: Optional[MCPConfig] = None
    tools: Optional[ToolsConfig] = ToolsConfig()
    env_info: Optional[EnvInfoConfig] = EnvInfoConfig()
    debug: Optional[DebugConfig] = DebugConfig()
    linked_programs: Optional[LinkedProgramsConfig] = LinkedProgramsConfig()

    model_config = {
        "extra": "forbid"  # Forbid extra fields
    }


class LLMProgram:
    """Compiler for LLM program configurations.
    
    This class handles loading, validating, and processing TOML program files
    into a format ready for LLMProcess instantiation.
    """

    def __init__(self,
                 model_name: str,
                 provider: str,
                 system_prompt: str,
                 parameters: Dict[str, Any] = None,
                 display_name: Optional[str] = None,
                 preload_files: Optional[List[str]] = None,
                 mcp_config_path: Optional[str] = None,
                 mcp_tools: Optional[Dict[str, List[str]]] = None,
                 tools: Optional[Dict[str, Any]] = None,
                 linked_programs: Optional[Dict[str, Union[str, 'LLMProgram']]] = None,
                 debug_tools: bool = False,
                 env_info: Optional[Dict[str, Any]] = None,  # Add environment info configuration
                 base_dir: Optional[Path] = None):
        """Initialize a program.
        
        Args:
            model_name: Name of the model to use
            provider: Provider of the model (openai, anthropic, or vertex)
            system_prompt: System prompt that defines the behavior of the process
            parameters: Dictionary of API parameters
            display_name: User-facing name for the process in CLI interfaces
            preload_files: List of file paths to preload into the system prompt as context
            mcp_config_path: Path to MCP servers configuration file
            mcp_tools: Dictionary mapping server names to tools to enable
            tools: Dictionary from the [tools] section in the TOML program
            linked_programs: Dictionary mapping program names to TOML program paths or compiled LLMProgram objects
            debug_tools: Enable detailed debugging output for tool execution
            env_info: Environment information configuration
            base_dir: Base directory for resolving relative paths in files
        """
        # Flag to track if this program has been fully compiled (including linked programs)
        self.compiled = False
        
        # Initialize core attributes
        self.model_name = model_name
        self.provider = provider
        self.system_prompt = system_prompt
        self.parameters = parameters or {}
        self.display_name = display_name or f"{provider.title()} {model_name}"
        self.preload_files = preload_files or []
        self.mcp_config_path = mcp_config_path
        self.mcp_tools = mcp_tools or {}
        self.tools = tools or {}
        self.linked_programs = linked_programs or {}
        self.debug_tools = debug_tools
        self.env_info = env_info or {"variables": []}  # Default to empty list (disabled)
        self.base_dir = base_dir
        
        # Extract API parameters from parameters for convenience
        self.api_params = self._extract_api_parameters()
        
    def _extract_api_parameters(self) -> Dict[str, Any]:
        """Extract known API parameters from the parameters dictionary.
        
        Returns:
            Dictionary of API parameters for LLM API calls
        """
        api_params = {}
        api_param_keys = [
            "temperature", "max_tokens", "top_p", 
            "frequency_penalty", "presence_penalty"
        ]
        
        for key in api_param_keys:
            if key in self.parameters:
                api_params[key] = self.parameters[key]
                
        return api_params
    
    @classmethod
    def compile(cls, toml_path: Union[str, Path], include_linked: bool = True, 
                check_linked_files: bool = True, return_all: bool = False) -> Union['LLMProgram', Dict[str, 'LLMProgram']]:
        """Compile an LLM program from a TOML file.
        
        This method loads a TOML file, validates the configuration, resolves file paths,
        and returns a compiled LLMProgram ready for instantiation of an LLMProcess.
        
        If include_linked=True, it will also compile all linked programs recursively
        and update the linked_programs attribute of each program to reference the 
        compiled program objects directly.
        
        Args:
            toml_path: Path to the TOML program file
            include_linked: Whether to compile linked programs recursively
            check_linked_files: Whether to verify linked program files exist
            return_all: Whether to return all compiled programs as a dictionary
            
        Returns:
            By default: A single compiled LLMProgram instance for the main program
            If return_all=True: Dictionary mapping absolute paths to compiled programs
            
        Raises:
            FileNotFoundError: If the TOML file or referenced files cannot be found
            ValidationError: If the configuration is invalid
            ValueError: If there are issues with configuration values
        """
        # Convert to Path object and resolve it
        path = Path(toml_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Program file not found: {toml_path}")
        
        # Get the global registry
        registry = ProgramRegistry()
        
        # Handle single program compilation (no linked programs)
        if not include_linked:
            # If already compiled, return from registry
            if registry.contains(path):
                return registry.get(path)
                
            # Otherwise compile and register it
            program = cls._compile_single_program(path)
            program.compiled = True
            registry.register(path, program)
            return program
        
        # Handle BFS compilation of the program graph
        abs_path = str(path)
        
        # If main program is already compiled and we're not returning all, just return it
        if registry.contains(path) and not return_all:
            return registry.get(path)
            
        # Stage 1: Compile all programs without resolving linked programs
        # This builds a complete set of all programs in the graph
        to_compile = deque([path])
        compiled_paths = set()  # Track what we've queued to avoid duplicates
        compiled_paths.add(abs_path)
        
        while to_compile:
            current_path = to_compile.popleft()
            
            # Skip if already compiled - just continue to queue its linked programs
            if not registry.contains(current_path):
                # Compile the current program
                program = cls._compile_single_program(current_path)
                registry.register(current_path, program)
            else:
                program = registry.get(current_path)
            
            # Find linked programs and add them to the compilation queue
            if hasattr(program, 'linked_programs') and program.linked_programs:
                base_dir = current_path.parent
                
                # At this stage, linked_programs contains string paths 
                for linked_name, linked_path_str in list(program.linked_programs.items()):
                    # Skip any non-string items (already processed linked programs)
                    if not isinstance(linked_path_str, str):
                        continue
                        
                    linked_path = Path(linked_path_str)
                    if not linked_path.is_absolute():
                        linked_path = base_dir / linked_path
                    
                    # Resolve to absolute path
                    linked_abs_path = linked_path.resolve()
                    
                    # Check if linked file exists (if checking is enabled)
                    if not check_linked_files or linked_path.exists():
                        # Only add to queue if we haven't seen it before
                        if str(linked_abs_path) not in compiled_paths:
                            to_compile.append(linked_path)
                            compiled_paths.add(str(linked_abs_path))
                    else:
                        # Raise error for missing linked program files
                        raise FileNotFoundError(f"Linked program file not found - From '{current_path}', "
                                              f"looking for '{linked_path_str}' (resolved to '{linked_path}')")
        
        # Stage 2: Update linked_programs to reference compiled program objects
        for compiled_path in compiled_paths:
            program = registry.get(Path(compiled_path))
            
            # Update any string paths to refer to compiled program objects
            if hasattr(program, 'linked_programs') and program.linked_programs:
                base_dir = Path(compiled_path).parent
                
                # Create a new dict for the updated references
                updated_links = {}
                
                for linked_name, linked_path_str in program.linked_programs.items():
                    # Skip if it's already a program object not a string
                    if not isinstance(linked_path_str, str):
                        updated_links[linked_name] = linked_path_str
                        continue
                        
                    # Resolve the path
                    linked_path = Path(linked_path_str)
                    if not linked_path.is_absolute():
                        linked_path = base_dir / linked_path
                        
                    # Get the compiled program from the registry
                    linked_program = registry.get(linked_path)
                    if linked_program:
                        updated_links[linked_name] = linked_program
                    else:
                        # Should never happen if Stage 1 completed successfully
                        warnings.warn(f"Could not find compiled program for {linked_path}")
                        updated_links[linked_name] = linked_path_str
                
                # Replace the linked_programs dict with the updated version
                program.linked_programs = updated_links
            
            # Mark the program as fully compiled
            program.compiled = True
        
        # Return either the main program or all compiled programs
        if return_all:
            return {path: registry.get(Path(path)) for path in compiled_paths}
        else:
            return registry.get(path)
    
    @classmethod
    def _compile_single_program(cls, path: Path) -> 'LLMProgram':
        """Compile a single program without recursively compiling linked programs.
        
        Args:
            path: Path to the TOML program file
            
        Returns:
            Compiled LLMProgram instance
        """
        # Load and parse the TOML file
        with path.open("rb") as f:
            raw_config = tomllib.load(f)
        
        # Validate the configuration using pydantic
        try:
            config = LLMProgramConfig(**raw_config)
        except ValidationError as e:
            # Enhance the validation error with file information
            error_msg = f"Invalid program configuration in {path}:\n{str(e)}"
            raise ValueError(error_msg)
        
        # Build the LLMProgram from the validated configuration
        program = cls._build_from_config(config, path.parent)
        
        # Store the source path
        program.source_path = path
        
        return program
    
    # Removed _load_system_prompt in favor of PromptConfig.resolve() method
        
    # Removed compile_all method in favor of the unified compile method
    
    @classmethod
    def _build_from_config(cls, config: LLMProgramConfig, base_dir: Path) -> 'LLMProgram':
        """Build an LLMProgram from a validated configuration.
        
        Args:
            config: Validated program configuration
            base_dir: Base directory for resolving relative file paths
            
        Returns:
            Constructed LLMProgram instance
            
        Raises:
            FileNotFoundError: If required files cannot be found
        """
        # Resolve system prompt using the PromptConfig's resolve method
        # This will raise FileNotFoundError if the system prompt file is specified but not found
        system_prompt = config.prompt.resolve(base_dir)
        
        # Resolve preload files
        preload_files = None
        if config.preload and config.preload.files:
            preload_files = []
            for file_path in config.preload.files:
                # Determine file path, using base_dir for relative paths
                resolved_path = base_dir / file_path
                if not resolved_path.exists():
                    # Only issue a warning at compile time, don't fail
                    warnings.warn(f"Preload file not found - Specified: '{file_path}', Resolved: '{resolved_path}'")
                # Include the file path regardless - it will be checked at runtime when actually loaded
                preload_files.append(str(resolved_path))
        
        # Resolve MCP configuration
        mcp_config_path = None
        if config.mcp and config.mcp.config_path:
            mcp_path = base_dir / config.mcp.config_path
            if not mcp_path.exists():
                raise FileNotFoundError(f"MCP config file not found - Specified: '{config.mcp.config_path}', Resolved: '{mcp_path}'")
            mcp_config_path = str(mcp_path)
        
        # Extract MCP tools configuration
        mcp_tools = None
        if config.mcp and config.mcp.tools:
            mcp_tools = config.mcp.tools.root
        
        # Process linked programs
        linked_programs = None
        if config.linked_programs:
            linked_programs = {}
            for program_name, program_path in config.linked_programs.root.items():
                linked_programs[program_name] = program_path
        
        # Extract environment info configuration
        env_info = config.env_info.model_dump() if config.env_info else {"variables": []}
        
        # Create the program instance
        program = cls(
            model_name=config.model.name,
            provider=config.model.provider,
            system_prompt=system_prompt,
            parameters=config.parameters,
            display_name=config.model.display_name,
            preload_files=preload_files,
            mcp_config_path=mcp_config_path,
            mcp_tools=mcp_tools,
            tools=config.tools.model_dump() if config.tools else None,
            linked_programs=linked_programs,
            env_info=env_info,
            base_dir=base_dir
        )
        
        return program
    
    def get_enriched_system_prompt(self, process_instance=None, include_env=True):
        """Get enhanced system prompt with preloaded files and environment info.
        
        This combines the basic system prompt with preloaded files and optional
        environment information based on the env_info configuration.
        
        Args:
            process_instance: Optional LLMProcess instance for accessing preloaded content
            include_env: Whether to include environment information (default: True)
            
        Returns:
            Complete system prompt ready for API calls
        """
        import os
        import datetime
        import platform
        from pathlib import Path
        
        # Start with the base system prompt
        enriched_prompt = self.system_prompt
        
        # Add environment info if variables are specified and include_env is True
        env_info = ""
        if include_env:
            variables = self.env_info.get("variables", [])
            
            # If variables is specified and not empty
            if variables:
                # Start the env section
                env_info = "<env>\n"
                
                # Handle standard variables based on the requested list or "all"
                all_variables = variables == "all"
                var_list = ["working_directory", "platform", "date", "python_version", "hostname", "username"] if all_variables else variables
                
                # Add standard environment information if requested
                if "working_directory" in var_list:
                    env_info += f"working_directory: {os.getcwd()}\n"
                    
                if "platform" in var_list:
                    env_info += f"platform: {platform.system().lower()}\n"
                    
                if "date" in var_list:
                    env_info += f"date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
                    
                if "python_version" in var_list:
                    env_info += f"python_version: {platform.python_version()}\n"
                    
                if "hostname" in var_list:
                    env_info += f"hostname: {platform.node()}\n"
                    
                if "username" in var_list:
                    import getpass
                    env_info += f"username: {getpass.getuser()}\n"
                
                # Add any custom environment variables
                for key, value in self.env_info.items():
                    # Skip the variables key and any non-string values
                    if key == "variables" or not isinstance(value, str):
                        continue
                    env_info += f"{key}: {value}\n"
                
                # Close the env section
                env_info += "</env>"
        
        # Add preloaded content if available
        preload_content = ""
        if process_instance and hasattr(process_instance, "preloaded_content"):
            if process_instance.preloaded_content:
                preload_content += "<preload>\n"
                for file_path, content in process_instance.preloaded_content.items():
                    filename = Path(file_path).name
                    preload_content += f'<file path="{filename}">\n{content}\n</file>\n'
                preload_content += "</preload>"
        
        # Combine all parts with proper spacing
        parts = [enriched_prompt]
        if env_info:
            parts.append(env_info)
        if preload_content:
            parts.append(preload_content)
            
        return "\n\n".join(parts)
    
    async def start(self) -> "LLMProcess":
        """Create and fully initialize an LLMProcess from this program.
        
        This is the recommended way to create a process from a program, as it
        properly handles async initialization for features like MCP tools.
        
        Returns:
            A fully initialized LLMProcess ready to run
            
        Raises:
            RuntimeError: If initialization fails
        """
        # Import dynamically to avoid circular imports
        import llmproc
        
        # Create a process and fully initialize it asynchronously
        process = await llmproc.LLMProcess.create(program=self)
        
        return process