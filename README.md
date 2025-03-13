# LLMProc

A simple, flexible framework for building LLM-powered applications with a standardized configuration approach.

## Features

- Load configurations from TOML files
- Maintain conversation state
- Support for different LLM providers (OpenAI initially)
- Extensive parameter customization
- Simple API for easy integration
- Command-line interface for interactive chat sessions
- Comprehensive documentation for all parameters

## Installation

```bash
# recommended
uv pip install -e .
# or
pip install -e .

# Set up environment variables
# supports .env file
OPENAI_API_KEY=your_api_key_here
```

## Usage

### Basic Example

```python
from llmproc import LLMProcess

# Load configuration from TOML
process = LLMProcess.from_toml('examples/minimal.toml')

# Run the process with user input
output = process.run('Hello!')
print(output)

# Continue the conversation
output = process.run('Tell me more about that.')
print(output)

# Reset the conversation state
process.reset_state()
```

### TOML Configuration

Minimal example:

```toml
[model]
name = "gpt-4o-mini"
provider = "openai"

[prompt]
system_prompt = "You are a helpful assistant."
```

See `examples/reference.toml` for a comprehensive reference with comments for all supported parameters.

## Command-Line Demo

LLMProc includes a simple command-line demo for interacting with LLM models:

```bash
# Start the interactive demo
llmproc-demo
```

The demo will:
1. Show a list of available TOML configurations from the examples directory
2. Let you select a configuration by number
3. Start an interactive chat session with the selected model

### Interactive Commands

In the interactive session, you can use the following commands:

- Type `exit` or `quit` to end the session
- Type `reset` to reset the conversation state

## License

MIT