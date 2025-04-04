# Python SDK

LLMProc provides a fluent, Pythonic SDK interface for creating and configuring LLM programs. This guide describes how to use the Python SDK features implemented in [RFC018](../RFC/RFC018_python_sdk.md).

## Fluent API

The fluent API allows for method chaining to create and configure LLM programs:

```python
from llmproc import LLMProgram

program = (
    LLMProgram(
        model_name="claude-3-haiku-20240307",
        provider="anthropic",
        system_prompt="You are a helpful assistant."
    )
    .add_tool(my_tool_function)
    .add_preload_file("context.txt")
    .add_linked_program("expert", expert_program, "An expert program")
)

# Start the process
process = await program.start()
```

## Program Creation and Configuration

### Basic Initialization

```python
from llmproc import LLMProgram

# Create a basic program
program = LLMProgram(
    model_name="gpt-4",
    provider="openai",
    system_prompt="You are a helpful assistant."
)
```

### Method Chaining

All configuration methods return `self` to allow for method chaining:

```python
# Configure a program with method chaining
program = (
    LLMProgram(...)
    .add_preload_file("file1.md")
    .add_preload_file("file2.md")
    .add_tool(tool_function)
    .configure_env_info(["working_directory", "platform", "date"])
    .configure_file_descriptor(max_direct_output_chars=10000)
    .configure_thinking(budget_tokens=8192)
)
```

### Program Linking

Link multiple specialized programs together:

```python
# Create specialized programs
math_program = LLMProgram(
    model_name="gpt-4",
    provider="openai",
    system_prompt="You are a math expert."
)

code_program = LLMProgram(
    model_name="claude-3-opus-20240229",
    provider="anthropic",
    system_prompt="You are a coding expert."
)

# Create a main program linked to the specialized programs
main_program = (
    LLMProgram(
        model_name="claude-3-haiku-20240307",
        provider="anthropic",
        system_prompt="You are a helpful assistant."
    )
    .add_linked_program("math", math_program, "Expert in mathematics")
    .add_linked_program("code", code_program, "Expert in coding")
)
```

### Compilation

All programs are compiled before starting:

```python
# Compile the program
program.compile()

# Start the process
process = await program.start()
```

compile() will load necessary files from the program configuration and raise error/warning if there's any issue. It will be called automatically when start() is called if the program is not compiled.

So you can call start() directly.

```python
process = await program.start()
```

## Advanced Configuration

### Environment Information

Configure which environment variables are included in the system prompt:

```python
# Include specific environment variables
program.configure_env_info(["working_directory", "platform", "date"])

# Include all standard environment variables
program.configure_env_info("all")

# Explicitly disable environment information
program.configure_env_info([])
```

### File Descriptor System

Configure the file descriptor system for handling large outputs:

```python
# Enable with default settings
program.configure_file_descriptor()

# Configure with custom settings
program.configure_file_descriptor(
    max_direct_output_chars=10000,
    default_page_size=5000,
    enable_references=True
)

# Disable file descriptor system
program.configure_file_descriptor(enabled=False)
```

### Claude 3.7 Thinking Models

Configure the thinking capability for Claude 3.7 models:

```python
# Enable thinking with default budget
program.configure_thinking()

# Enable thinking with custom budget
program.configure_thinking(budget_tokens=8192)

# Disable thinking
program.configure_thinking(enabled=False)
```

### Token-Efficient Tools

Enable token-efficient tool use for Claude 3.7 models:

```python
# Enable token-efficient tools
program.enable_token_efficient_tools()
```

### MCP Tools

Configure Model Context Protocol (MCP) tools:

```python
# Enable specific tools from servers
program.configure_mcp(
    config_path="config/mcp_servers.json",
    tools={
        "sequential-thinking": "all",
        "github": ["search_repositories", "get_file_contents"]
    }
)

# Enable only MCP configuration without tools
program.configure_mcp(config_path="config/mcp_servers.json")
```

## Function-Based Tools

LLMProc supports registering Python functions as tools with automatic schema generation from type hints and docstrings. This allows you to easily integrate custom Python functionality with your LLM programs.

For detailed documentation on function-based tools, including:
- Basic usage and examples
- The `register_tool` decorator
- Type conversion from Python types to JSON schema
- Support for both synchronous and asynchronous functions
- Parameter validation and error handling

See the dedicated [Function-Based Tools](function-based-tools.md) documentation.

A complete working example is also available in [examples/features/function_tools.py](../examples/features/function_tools.py).