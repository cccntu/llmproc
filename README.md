# LLMProc

A simple, flexible framework for building LLM-powered applications with a standardized configuration approach.

> **Note**: For detailed implementation notes, advanced usage, limitations, and more, see [MISC.md](MISC.md).

# LLMProc Design Philosophy

## Core Principles

### LLM as Process

We view LLMs as processes in a computing environment:
- Each process is defined by a program (TOML file)
- It receives input, executes, and returns output
- It maintains state between executions
- It interacts with the system through defined interfaces

### LLMProc as Kernel

The LLMProc library functions as a kernel:
- Implements system calls for LLM processes
- Manages resources across processes
- Provides privileged operations processes cannot perform themselves
- Creates a standardized interface between processes and their environment

## Features

- Load and validate programs from TOML files with robust error checking
- Maintain conversation state
- Support for different LLM providers (OpenAI, Anthropic, Anthropic on Vertex AI)
- Extensive parameter customization
- Simple API for easy integration
- Command-line interface for interactive chat sessions
- Comprehensive documentation for all parameters
- File preloading for context enhancement by adding content to system prompt
- Environment information sharing for context-aware LLMs
- Model Context Protocol (MCP) support for tool usage
- Program Linking for LLM-to-LLM communication via spawn tool (like `dispatch_agent` in Claude Code)
- Program Compiler for robust validation and preprocessing of configurations
- File Descriptor system for handling large tool outputs with pagination

## Installation

```bash
# recommended
uv pip install -e .
# or
pip install -e .

# Set up environment variables
# supports .env file
# supports OPENAI_API_KEY, ANTHROPIC_API_KEY, ANTHROPIC_VERTEX_PROJECT_ID, CLOUD_ML_REGION
```

## Supported Providers

### OpenAI
- Requires `OPENAI_API_KEY` environment variable
- Supports all GPT models (gpt-3.5-turbo, gpt-4o, etc.)

### Anthropic
- Requires `ANTHROPIC_API_KEY` environment variable
- Supports all Claude models (claude-3-haiku, claude-3-opus, etc.)

### Anthropic on Vertex AI
- Requires `ANTHROPIC_VERTEX_PROJECT_ID` and `CLOUD_ML_REGION` environment variables
- Google Cloud authentication must be set up (gcloud auth)
- Supports Claude models deployed on Google Cloud Vertex AI
- See [Anthropic Documentation](docs/anthropic.md) for details

## Usage

### Basic Example

```python
import asyncio
from llmproc import LLMProgram

async def main():
    # Load program from TOML (recommended approach)
    program = LLMProgram.from_toml('examples/minimal.toml')

    # Start the process asynchronously
    process = await program.start()

    # Run the process with user input
    run_result = await process.run('Hello!')
    response = process.get_last_message()
    print(response)

    # Continue the conversation
    run_result = await process.run('Tell me more about that.')
    response = process.get_last_message()
    print(response)

    # Reset the conversation state
    process.reset_state()

# Run the async example
asyncio.run(main())
```

You can also create a process from a manually constructed program:

```python
import asyncio
from llmproc import LLMProgram

async def main():
    # Create a program
    program = LLMProgram(
        model_name="claude-3-haiku-20240307",
        provider="anthropic",
        system_prompt="You are a helpful assistant.",
        display_name="My Assistant",
        parameters={"temperature": 0.7}
    )

    # Start the process asynchronously
    process = await program.start()

    # Use the process
    response = await process.run("Hello, how can you help me?")
    print(response)

# Run the example
asyncio.run(main())
```

### Program Compiler Example

The program is compiled at initialization and provides validation and preprocessing of TOML configurations:

```python
from llmproc import LLMProgram

# Compile a program with validation
# from_toml is a thin wrapper wround .compile.
program = LLMProgram.compile('examples/minimal.toml')

# Access program properties
print(f"Model: {program.model_name}")
print(f"Provider: {program.provider}")
print(f"API Parameters: {program.api_params}")

# Start the process from the compiled program
process = program.start()
```

### TOML Program Format

Minimal example:

```toml
[model]
name = "gpt-4o-mini"
provider = "openai"

[prompt]
system_prompt = "You are a helpful assistant."

# Optional: Add environment information for context awareness
[env_info]
variables = ["working_directory", "platform", "date"]
```

See **`examples/reference.toml`** for a comprehensive reference with comments for all supported parameters and **`docs/env_info.md`** for detailed documentation on the environment information feature.

## Command-Line Demo

LLMProc includes a command-line interface for interacting with LLM models. The `llmproc-demo` command provides an intuitive way to test different models and configurations.

### Quick Start

```bash
# Install the package
uv pip install -e .  # or pip install -e .

# Set up your API keys (required)
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
# For Vertex AI (optional)
export ANTHROPIC_VERTEX_PROJECT_ID="your-project-id" 
export CLOUD_ML_REGION="us-central1"

# Launch interactive demo
llmproc-demo
```

### Usage Examples

#### Interactive Mode

The default mode starts an interactive chat session:

```bash
# Select from example programs
llmproc-demo

# Use a specific program file
llmproc-demo ./examples/minimal.toml

# Chat with Claude (requires ANTHROPIC_API_KEY)
llmproc-demo ./examples/anthropic.toml
```

Example interactive session:

```
LLMProc CLI Demo
----------------

Available programs:
1. anthropic.toml
2. anthropic_vertex.toml
3. calculator.toml
...

Select a program (number): 1

Program Summary:
  Model: claude-3-haiku-20240307
  Provider: anthropic
  Display Name: Claude Haiku Assistant
  System Prompt: You are a helpful assistant.
  Temperature: 0.7

Starting interactive chat session. Type 'exit' or 'quit' to end.
Type 'reset' to reset the conversation state.
Type 'verbose' to toggle verbose logging.

You> What can you do for me?

Claude Haiku Assistant> I can help with a wide range of tasks including:
- Answering questions on various topics
- Explaining complex concepts
- Writing and editing text
- Summarizing information
- Providing creative ideas
- Offering thoughtful advice
- Discussing different perspectives on topics

Just let me know what you need assistance with!

You> exit
Ending session.
```

#### Non-Interactive Mode

For single prompts or scripting:

```bash
# One-off prompt (returns a single response)
llmproc-demo ./examples/openai.toml -p "Explain the concept of LLMs in one sentence"

# Read from stdin (pipe mode)
echo "What is Python?" | llmproc-demo ./examples/minimal.toml -n

# Process a file
cat questions.txt | llmproc-demo ./examples/anthropic.toml -n
```

Example output:

```
$ llmproc-demo ./examples/minimal.toml -p "Explain LLMs in one sentence"

Large Language Models are neural networks trained on vast amounts of text data that can understand, generate, and manipulate human language based on the patterns they've learned.
```

#### Advanced Features

```bash
# Use Claude Code's dispatch_agent and other tools
llmproc-demo ./examples/claude_code.toml

# Try Program Linking (LLM-to-LLM communication)
llmproc-demo ./examples/program_linking/main.toml

# Use the calculator tool
llmproc-demo ./examples/calculator.toml

# Try using the fork feature
llmproc-demo ./examples/fork.toml

# Try using the file descriptor system
llmproc-demo ./examples/file_descriptor.toml
```

Example program linking session:

```
You> Ask the repo expert how the program compiler works

Main Assistant> I'll ask the repo expert about the program compiler.

The repo expert explains that the program compiler in LLMProc handles validation and preprocessing of TOML configurations. It uses a two-phase approach: first compiling individual programs and then linking them together. The compiler validates configuration parameters, resolves file paths, preprocesses system prompts, and handles tool registrations. It also manages a global program registry to prevent duplicate compilation and detects circular dependencies in program linking.

You> What files implement the program compiler?

Main Assistant> Let me ask the repo expert about the program compiler implementation files.

According to the repo expert, the program compiler is primarily implemented in:
1. src/llmproc/program.py - Contains the LLMProgram class with compile methods
2. src/llmproc/config/schema.py - Defines Pydantic models for validation
3. src/llmproc/config/utils.py - Provides path resolution utilities

The main implementation is in program.py where the compile() and compile_all() methods handle the compilation process.
```

### Interactive Commands

During an interactive session, you can use these special commands:

- `exit` or `quit` - End the session
- `reset` - Clear the conversation history and start fresh
- `verbose` - Toggle detailed logging (shows API calls, timing, etc.)

### Available Examples

The `examples/` directory contains ready-to-use program files:

- `minimal.toml` - Bare minimum configuration with OpenAI
- `anthropic.toml` - Basic Claude configuration
- `openai.toml` - Basic OpenAI configuration
- `claude_code.toml` - Claude with coding tools enabled
- `calculator.toml` - Demonstrates the calculator tool
- `program_linking/main.toml` - Demonstrates LLM-to-LLM communication
- `fork.toml` - Shows the fork system call in action
- `preload.toml` - Demonstrates file preloading feature
- `file_descriptor.toml` - Shows the file descriptor system for handling large outputs
- `reference.toml` - Full reference with all available options

### CLI Options

```
Usage: llmproc-demo [OPTIONS] [PROGRAM_PATH]

  Run a simple CLI for LLMProc.

  PROGRAM_PATH is an optional path to a TOML program file.
  If not provided, you'll be prompted to select from available examples.

  Supports three modes:
  1. Interactive mode (default): Chat continuously with the model
  2. Non-interactive with prompt: Use --prompt/-p "your prompt here"
  3. Non-interactive with stdin: Use --non-interactive/-n and pipe input

Options:
  -p, --prompt TEXT  Run in non-interactive mode with the given prompt
  -n, --non-interactive  Run in non-interactive mode (reads from stdin if no
                     prompt provided)
  --help             Show this message and exit
```

## Implementation Details

### Program Definition via TOML

- Makes process definitions portable across implementations
- Enables program modification (similar to Claude Code updating CLAUDE.md)
- Human-readable and LLM-friendly format

### Testing

LLMProc has a comprehensive test suite for all components:
- Unit tests for core functionality without requiring API keys
- Integration tests for program features
- API tests for verifying actual LLM integration (requires API keys)

See [Testing Guide](docs/testing.md) for details on running and writing tests.

### System Calls

LLMProc implements Unix-like process system calls:
- **spawn**: Create new processes from linked programs (analogous to exec()) - ✅ Implemented
- **fork**: Duplicate an existing process with its state (analogous to fork()) - ✅ Implemented
- **read_fd**: Read content from file descriptors (analogous to read()) - ✅ Implemented
- **read_file**: Simple file reading capability (for demonstration) - ✅ Implemented

Reference: [forking-an-agent](https://github.com/cccntu/forking-an-agent)

### Program Linking

Program linking allows one LLM process to communicate with other specialized LLM processes:

```toml
# Main.toml - Configure main process with spawn system call
[tools]
enabled = ["spawn"]

[linked_programs]
expert = "path/to/expert.toml"
```

This enables:
- Creating specialized processes with domain-specific knowledge
- Delegating queries to the most appropriate process
- Centralized knowledge repository with distributed querying

### MCP Integration

- System calls are implemented in the LLMProc kernel

### File Descriptor System

The file descriptor system provides a Unix-like solution for handling large tool outputs:

```toml
# Enable file descriptor tools
[tools]
enabled = ["read_fd"]

# Configure the file descriptor system
[file_descriptor]
enabled = true                  # Explicitly enable (also enabled by read_fd in tools)
max_direct_output_chars = 8000  # Threshold for FD creation
default_page_size = 4000        # Size of each page
```

Key features:
- Automatic wrapping of large tool outputs into file descriptors
- Line-aware pagination with continuation indicators
- XML-formatted responses with metadata
- Preservation of FDs during fork operations
- Read interface via read_fd system call
- "Userspace" tools are provided via MCP
- MCP provides a standard protocol for tools that's independent of the LLMProc implementation

## Roadmap

1. [x] Implement Program Linking via Spawn Tool
2. [x] Implement Fork System Call
3. [ ] Implement Prompt Caching, Cost Tracking
4. [x] Implement Environment Variables
5. [ ] Implement File Descriptor
6. [ ] Implement Exec System Call for process replacement
7. [ ] Implement GOTO for program flow control
8. [ ] Improve OpenAI integration (MCP support)
9. [ ] Add support for reasoning models
10. [ ] Add Process State Serialization & Restoration
11. [ ] Implement retry mechanism with exponential backoff for API calls
12. [ ] Enhance error handling and reporting across providers
13. [ ] Improve stream mode support for all providers

## License

Apache License 2.0