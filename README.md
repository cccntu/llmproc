# LLMProc

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Status](https://img.shields.io/badge/status-active-green)

A Unix-inspired framework for building powerful LLM applications that lets you spawn specialized models, manage large outputs, and enhance context with file preloading.

> LLMProc treats language models as processes: spawn them, fork them, link them together, and handle their I/O with a familiar Unix-like approach.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Features](#features)
- [Demo Tools](#demo-tools)
- [Documentation](#documentation)
- [Design Philosophy](#design-philosophy)
- [Roadmap](#roadmap)
- [License](#license)

## Installation

```bash
# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .

# Set environment variables
export OPENAI_API_KEY="your-key"    # For OpenAI models
export ANTHROPIC_API_KEY="your-key"  # For Claude models
```

The package supports `.env` files for environment variables.

## Quick Start

### Python usage

```python
import asyncio
from llmproc import LLMProgram, register_tool

@register_tool()
def calculate(expression: str) -> dict:
    return {"result": eval(expression, {"__builtins__": {}})}

async def main():
    # You can load a program from a TOML file
    program = LLMProgram.from_toml('examples/anthropic/claude-3-5-haiku.toml')

    # Or create a program with the python API
    program = (
        LLMProgram(
            model_name="claude-3-7-sonnet-20250219",
            provider="anthropic",
            system_prompt="You are a helpful assistant."
        )
        .add_tool(calculate)
    )

    # Start and use the process
    process = await program.start()
    result = await process.run('What is 125 * 48?')
    print(process.get_last_message())

asyncio.run(main())
```

### CLI usage

```bash
# Start interactive session
llmproc-demo ./examples/anthropic/claude-3-5-haiku.toml

# Single prompt
llmproc-demo ./examples/anthropic/claude-3-5-sonnet.toml -p "What is Python?"

# Read from stdin
cat questions.txt | llmproc-demo ./examples/anthropic/claude-3-7-sonnet.toml -n
```

## Features

LLMProc offers a complete toolkit for building sophisticated LLM applications:

### Basic Configuration
- **[Minimal Setup](./examples/anthropic/claude-3-5-haiku.toml)** - Start with a simple Claude configuration
- **[File Preloading](./examples/features/preload.toml)** - Enhance context by loading files into system prompts
- **[Environment Info](./examples/features/env-info.toml)** - Add runtime context like working directory and platform

### Developer Experience
- **[Python SDK](./docs/python-sdk.md)** - Create programs with intuitive method chaining
- **[Function-Based Tools](./docs/function-based-tools.md)** - Register Python functions as tools with type-safety and auto-conversion

### Process Management
- **[Program Linking](./examples/features/program-linking/main.toml)** - Spawn and delegate tasks to specialized LLM processes
- **[Fork Tool](./examples/features/fork.toml)** - Create process copies with shared conversation state

### Large Content Handling
- **[File Descriptor System](./examples/features/file-descriptor/main.toml)** - Unix-like pagination for large outputs

### More Features
- **Prompt Caching** - Automatic 90% token savings for Claude models (enabled by default)
- **Reasoning/Thinking models** - [Claude 3.7 Thinking](./examples/anthropic/claude-3-7-thinking-high.toml) and [OpenAI Reasoning](./examples/openai/o3-mini-high.toml) models
- **[MCP Protocol](./examples/features/mcp.toml)** - Standardized interface for tool usage
- **Cross-provider support** - Currently supports Anthropic, OpenAI, and Anthropic on Vertex AI

## Demo Tools

LLMProc includes demo command-line tools for quick experimentation:

### llmproc-demo

Interactive CLI for testing LLM configurations:

```bash
llmproc-demo ./examples/anthropic/claude-3-5-haiku.toml  # Interactive session
llmproc-demo ./config.toml -p "What is Python?"          # Single prompt
cat questions.txt | llmproc-demo ./config.toml -n        # Pipe mode
```

Commands: `exit` or `quit` to end the session

### llmproc-prompt

View the compiled system prompt without making API calls:

```bash
llmproc-prompt ./config.toml                 # Display to stdout
llmproc-prompt ./config.toml -o prompt.txt   # Save to file
llmproc-prompt ./config.toml -E              # Without environment info
```

## Use Cases
- **[Claude Code](./examples/claude-code/claude-code.toml)** - A minimal Claude Code implementation, with support for preloading CLAUDE.md, spawning, MCP

## Documentation

- [Examples](./examples/README.md): Sample configurations and use cases
- [API Docs](./docs/api/index.md): Detailed API documentation
- [Python SDK](./docs/python-sdk.md): Fluent API and program creation
- [Function-Based Tools](./docs/function-based-tools.md): Python function tools with type hints
- [File Descriptor System](./docs/file-descriptor-system.md): Handling large outputs
- [Program Linking](./docs/program-linking.md): LLM-to-LLM communication
- [MCP Feature](./docs/mcp-feature.md): Model Context Protocol for tools
- [Testing Guide](./docs/testing.md): Testing and validation
- For complete reference, see [reference.toml](./examples/reference.toml)

For advanced usage and implementation details, see [MISC.md](MISC.md).

## Design Philosophy

LLMProc treats LLMs as computing processes:
- Each model is a process defined by a program (TOML file)
- It maintains state between executions
- It interacts with the system through defined interfaces

The library functions as a kernel:
- Implements system calls for LLM processes
- Manages resources across processes
- Creates a standardized interface with the environment

## Roadmap

Future development plans:

1. Exec System Call for process replacement
2. Process State Serialization & Restoration
3. Retry mechanism with exponential backoff
4. Enhanced error handling and reporting
5. Support for streaming
6. File Descriptor System Phase 3 enhancements
7. Gemini models support

## License

Apache License 2.0