# Model Context Protocol (MCP) Feature

The Model Context Protocol (MCP) feature integrates tool usage capabilities with LLM models, allowing LLMs to use external tools to perform actions like searching the web, accessing GitHub repositories, reading files, and more.

## Overview

MCP provides a standardized way for LLM agents to interact with external tools. This feature enables the LLMProcess to:

1. Connect to MCP servers through a central registry
2. Register specific tools with the LLM model
3. Handle tool calls during model generation
4. Process tool results and continue the conversation

## Implementation Architecture

The MCP implementation uses a two-registry design for performance and isolation:

1. **MCP Manager**: Centralizes MCP server and tool management
   - Handles selective initialization of MCP servers and tools
   - Only launches servers needed for requested tools
   - Maintains separation between MCP tools and runtime tools
   - Enforces access control for MCP tools

2. **Dual-Registry Approach**:
   - **MCP Registry**: Manages tool definitions from MCP servers
   - **Runtime Registry**: Stores runtime-accessible tools
   - Tools are copied from MCP registry to runtime registry during initialization
   - This separation improves performance and resource usage

## Configuration

MCP is configured through the TOML configuration file with dedicated sections for server configuration and tools:

```toml
[mcp]
config_path = "config/mcp_servers.json"

[tools.mcp]
github = ["search_repositories", "get_file_contents"]
codemcp = ["ReadFile"]
```

### Configuration Options

- `[mcp]` section:
  - `config_path`: Path to the MCP servers configuration JSON file
- `[tools.mcp]` section: Dictionary of server names mapped to tools to enable
  - Server name = List of specific tools to import OR "all" to import all tools from that server

### MCP Servers Configuration

The MCP servers configuration file specifies the servers to connect to:

```json
{
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-github"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "codemcp": {
      "type": "stdio",
      "command": "/bin/zsh",
      "args": [
        "-c",
        "uvx --from git+https://github.com/cccntu/codemcp@main codemcp "
      ]
    }
  }
}
```

## Tool Filtering

Users must explicitly specify which tools they want to import from each server. Even if the MCP config file includes many servers, only the explicitly specified tools will be added to the LLM process. This is enforced for security and performance reasons.

You can specify tools in two ways:

1. List specific tools: `github = ["search_repositories", "get_file_contents"]`
2. Import all tools from a server: `github = "all"`

### Using MCPTool API

You can also programmatically register MCP tools with access control using the `MCPTool` class:

```python
from llmproc.common.access_control import AccessLevel
from llmproc.tools.mcp import MCPTool

# Register MCP tools with different access levels
program.register_tools([
    # All tools from server with default WRITE access
    MCPTool(server="calculator"),
    
    # Specific tools with READ access
    MCPTool(server="github", names=["search_repos"], access=AccessLevel.READ),
    
    # Different access levels for different tools
    MCPTool(server="file_server", names={
        "read_file": AccessLevel.READ,
        "write_file": AccessLevel.WRITE,
        "delete_file": AccessLevel.ADMIN
    })
])
```

## Provider Support

Currently, MCP functionality is only supported with the Anthropic provider. Support for OpenAI providers will be added in a future update.

## Example Usage

### TOML Configuration

```toml
[model]
name = "claude-3-haiku-20240307"
provider = "anthropic"
display_name = "Claude MCP Assistant"

[parameters]
temperature = 0.7
max_tokens = 300

[prompt]
system_prompt = "You are a helpful assistant with access to tools. Use tools whenever appropriate to answer user queries accurately."

[mcp]
config_path = "config/mcp_servers.json"

[tools.mcp]
github = ["search_repositories", "get_file_contents"]
codemcp = ["ReadFile"]
```

### Usage with Async/Await (Recommended)

For best performance and proper tool execution, use the `run` method with async/await:

```python
import asyncio
from llmproc import LLMProgram

async def main():
    # Step 1: Load and compile the program
    program = LLMProgram.from_toml("examples/mcp.toml")
    
    # Step 2: Initialize the process (handles async MCP setup)
    process = await program.start()
    
    # Use the process with full tool execution support
    result = await process.run("Please search for popular Python repositories on GitHub.")
    print(process.get_last_message())

# Run the async function
asyncio.run(main())
```

### Usage in Synchronous Code

The `run` method can also be used in synchronous code, and will automatically create an event loop:

```python
from llmproc import LLMProgram

# Step 1: Load and compile the program
program = LLMProgram.from_toml("examples/mcp.toml")

# Step 2: Initialize the process (creates event loop internally)
process = program.start()

# The run method can be used in synchronous code and will still support tools
# It automatically creates an event loop when needed
result = process.run("Please search for popular Python repositories on GitHub.")
print(process.get_last_message())
```

### Complete Example

See the TOML configuration in `examples/mcp.toml`, which demonstrates MCP tool configuration.

## Implementation Details

The implementation includes:

1. Extending LLMProcess to handle MCP configuration
2. Tool registration and filtering based on user configuration
3. Handling tool calls in Anthropic API responses
4. Processing tool results and continuing the conversation

Tools are initialized asynchronously when the LLMProcess is created, allowing for dynamic tool discovery and initialization.

## Future Enhancements

- Support for OpenAI's function calling API
- Enhanced tool call formatting and debugging
- Custom tool implementations
- Persistent tool state across conversation turns