# API Patterns and Best Practices

This document outlines the recommended patterns and best practices for using and extending the LLMProc library.

## Core Usage Patterns

### Standard Async Pattern

The primary usage pattern is fully async:

```python
import asyncio
from llmproc import LLMProgram

async def main():
    # Load and compile
    program = LLMProgram.from_toml("path/to/config.toml")
    
    # Start with async initialization
    process = await program.start()
    
    # Run and get metrics
    run_result = await process.run("User input")
    
    # Get the response text
    response = process.get_last_message()
    print(f"Response: {response}")

# Run the async function
asyncio.run(main())
```

### Handling RunResult

Always use the RunResult object for metrics and diagnostics:

```python
run_result = await process.run("User input")

print(f"Run completed in {run_result.duration_ms}ms")
print(f"API calls: {run_result.api_calls}")

# Detailed API information
for i, api_info in enumerate(run_result.api_call_infos):
    print(f"API call {i+1} details:")
    for key, value in api_info.items():
        print(f"  {key}: {value}")
```

### Using Callbacks

Register callbacks to monitor execution in real-time:

```python
callbacks = {
    "on_tool_start": lambda tool_name, args: print(f"Starting tool: {tool_name}"),
    "on_tool_end": lambda tool_name, result: print(f"Tool completed: {tool_name}"),
    "on_response": lambda content: print(f"Response: {content[:30]}...")
}

run_result = await process.run("User input", callbacks=callbacks)
```

## Extension Patterns

### Adding a New Tool

```python
# 1. Define the tool schema
my_tool_def = {
    "name": "my_tool",
    "description": "A custom tool that does X",
    "input_schema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Parameter 1"},
            "param2": {"type": "number", "description": "Parameter 2"}
        },
        "required": ["param1"]
    }
}

# 2. Create the handler function
async def my_tool_handler(args: dict) -> Any:
    param1 = args.get("param1", "")
    param2 = args.get("param2", 0)
    
    # Tool implementation
    result = f"Processed {param1} with value {param2}"
    
    return {"result": result, "success": True}

# 3. Register with the tool registry
def register_my_tool(registry, process):
    registry.register_tool("my_tool", my_tool_handler, my_tool_def)

# 4. Add to the registration system
def register_system_tools(registry, process):
    # ... existing code ...
    
    # Register custom tool if enabled
    if "my_tool" in process.enabled_tools:
        register_my_tool(registry, process)
```

### Adding a New Provider

```python
# 1. Create provider client factory in providers.py
def get_my_provider_client(model_name: str, **kwargs) -> Any:
    # Import necessary client library
    from my_provider_lib import Client
    
    # Get API key
    api_key = os.environ.get("MY_PROVIDER_API_KEY")
    if not api_key:
        raise ValueError("MY_PROVIDER_API_KEY environment variable not set")
    
    # Create and return client
    return Client(api_key=api_key)

# 2. Create a process executor class
class MyProviderProcessExecutor:
    async def run(self, process, user_prompt, max_iterations=10, 
                  callbacks=None, run_result=None):
        # Create a RunResult if not provided
        if run_result is None:
            from llmproc.results import RunResult
            run_result = RunResult()
        
        # Implementation specific to this provider
        # ...
        
        # Add API call info
        run_result.add_api_call({
            "model": process.model_name,
            "usage": response.usage
        })
        
        # Complete and return the result
        return run_result.complete()

# 3. Update the provider mapping in LLMProcess._async_run
elif self.provider == "my_provider":
    executor = MyProviderProcessExecutor()
    return await executor.run(self, user_prompt, max_iterations, callbacks, run_result)
```

## Best Practices

### Program Configuration

1. **File Organization**:
   - Keep all TOML program files in a dedicated directory (e.g., `programs/`)
   - Use clear, descriptive names for program files

2. **Configuration Structure**:
   - Group related settings in the appropriate TOML sections
   - Include comments to explain non-obvious settings

3. **System Prompts**:
   - Place long system prompts in separate files
   - Use [prompt] section with system_prompt_file instead of inline

### Process Execution

1. **State Management**:
   - Use reset_state() between conversation sessions
   - Keep preloaded content when appropriate with keep_preloaded=True

2. **Error Handling**:
   - Always use try/except around process.run() calls
   - Handle specific exceptions separately from general errors

3. **Resource Management**:
   - Monitor API calls with RunResult.api_calls
   - Track duration to identify performance issues

### Tool Development

1. **Tool Design**:
   - Keep tools focused on a single responsibility
   - Provide clear descriptions and parameter documentation
   - Use consistent naming conventions

2. **Tool Handler Implementation**:
   - Make handlers asynchronous (async def)
   - Add proper error handling inside handlers
   - Return structured results

3. **Tool Registration**:
   - Register tools only when enabled
   - Use the standard registration pattern
   - Include tools in the enabled list in TOML configuration

### Callback Usage

1. **Performance**:
   - Keep callbacks lightweight to avoid slowing down execution
   - Use async callbacks for heavy processing

2. **Error Handling**:
   - Add try/except inside callbacks to prevent disrupting execution
   - Log errors rather than raising exceptions

3. **UI Integration**:
   - Use callbacks for updating progress displays
   - Consider debouncing rapidly firing callbacks

## Anti-Patterns to Avoid

### ❌ Direct Process Creation

```python
# DON'T do this
process = LLMProcess(program=program)
```

Instead, use the program.start() method for proper async initialization:

```python
# DO this
process = await program.start()
```

### ❌ Ignoring RunResult

```python
# DON'T do this
await process.run("User input")
response = process.get_last_message()
```

Instead, capture and use the RunResult:

```python
# DO this
run_result = await process.run("User input")
response = process.get_last_message()
print(f"Used {run_result.api_calls} API calls")
```

### ❌ Synchronous Blocking

```python
# DON'T do this
def main():
    program = LLMProgram.from_toml("config.toml")
    process = asyncio.run(program.start())  # Blocking in sync function
```

Instead, use proper async patterns:

```python
# DO this
async def main():
    program = LLMProgram.from_toml("config.toml")
    process = await program.start()

asyncio.run(main())
```

### ❌ Direct State Manipulation

```python
# DON'T do this
process.state.append({"role": "user", "content": "Message"})
```

Instead, use the API methods:

```python
# DO this
await process.run("Message")
```