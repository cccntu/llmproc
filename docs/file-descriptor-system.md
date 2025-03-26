# File Descriptor System

The file descriptor system provides a Unix-like mechanism for handling large content (tool outputs, file contents, etc.) that would otherwise exceed the context window limit.

## Overview

When a tool produces output that's too large to fit directly into the context window, the file descriptor system:

1. Stores the content in memory with a simple identifier (fd:1, fd:2, etc.)
2. Returns a preview with the file descriptor reference
3. Allows the LLM to read the full content in pages using the `read_fd` tool

This system is inspired by Unix file descriptors and is designed to be intuitive for LLMs to understand and use.

## Design

For detailed design documentation, see the RFC files:
- [RFC001: File Descriptor System for LLMProc](/RFC/RFC001_file_descriptor_system.md): Primary design document
- [RFC003: File Descriptor Implementation Details](/RFC/RFC003_file_descriptor_implementation.md): Technical implementation details
- [RFC004: File Descriptor Implementation Phases](/RFC/RFC004_fd_implementation_phases.md): Implementation phases
- [RFC005: File Descriptor Integration with Spawn Tool](/RFC/RFC005_fd_spawn_integration.md): Integration with spawn system call
- [RFC006: Response Reference ID System](/RFC/RFC006_response_reference_id.md): Reference ID system for response content
- [RFC007: Enhanced File Descriptor API Design](/RFC/RFC007_fd_enhanced_api_design.md): Enhanced API features

## Configuration

The file descriptor system is configured through two mechanisms:

### 1. Tool Configuration

```toml
[tools]
enabled = ["read_fd", "fd_to_file"]  # FD reading and file export capability
```

### 2. File Descriptor Settings

```toml
[file_descriptor]
enabled = true                      # Explicitly enable (also enabled by read_fd in tools)
max_direct_output_chars = 2000      # Threshold for FD creation
default_page_size = 1000            # Size of each page
max_input_chars = 2000              # Threshold for user input FD creation (future)
page_user_input = true              # Enable/disable user input paging (future)
```

**Note**: The system is enabled if any FD tool is in `[tools].enabled` OR `enabled = true` exists in the `[file_descriptor]` section.

## Usage

### Basic File Descriptor Operations

```python
# Read a specific page
read_fd(fd="fd:1", page=2)

# Read the entire content
read_fd(fd="fd:1", read_all=True)

# Export content to a file
fd_to_file(fd="fd:1", file_path="/path/to/output.txt")
```

### XML Response Format

File descriptor operations use XML formatting for clarity:

```xml
<!-- Initial FD creation result -->
<fd_result fd="fd:1" pages="5" truncated="true" lines="1-42" total_lines="210">
  <message>Output exceeds 2000 characters. Use read_fd to read more pages.</message>
  <preview>
  First page content is included here...
  </preview>
</fd_result>

<!-- Read FD result -->
<fd_content fd="fd:1" page="2" pages="5" continued="true" truncated="true" lines="43-84" total_lines="210">
Second page content goes here...
</fd_content>

<!-- File export result -->
<fd_file_result fd="fd:1" file_path="/path/to/output.txt" char_count="12345" size_bytes="12345" success="true">
  <message>File descriptor fd:1 content (12345 chars) successfully written to /path/to/output.txt</message>
</fd_file_result>
```

### Key Features

- **Line-Aware Pagination**: Breaks content at line boundaries when possible
- **Continuation Indicators**: Shows if content continues across pages 
- **Sequential IDs**: Simple fd:1, fd:2, etc. pattern
- **Recursive Protection**: File descriptor tools don't trigger recursive FD creation
- **Filesystem Export**: Can save file descriptor content to disk files
- **Parent Directory Creation**: Automatically creates directories when exporting to files

## Implementation

The file descriptor system is implemented in `src/llmproc/tools/file_descriptor.py` with these key components:

1. **FileDescriptorManager**: Core class managing creation and access
2. **read_fd Tool**: System call interface for accessing content
3. **fd_to_file Tool**: System call interface for exporting content to files
4. **XML Formatting**: Standard response format with metadata

### Integration

The file descriptor system integrates with:

- **LLMProcess**: Initializes and maintains FD manager state
- **AnthropicProcessExecutor**: Automatically wraps large outputs
- **fork_process**: Maintains FD state during process forking

## Implementation Status

The current implementation status is tracked in [RFC004: File Descriptor Implementation Phases](/RFC/RFC004_fd_implementation_phases.md). Below is a summary as of 2025-03-25:

### ✅ Phase 1: Core Functionality (Completed)

The file descriptor system has completed Phase 1 implementation, which includes:

- Basic File Descriptor Manager with in-memory storage
- read_fd tool with page-based access
- Line-aware pagination with boundary detection
- Automatic tool output wrapping
- XML formatting with consistent metadata
- System prompt instructions

### 🔄 Phase 2: Process Integration (Partially Completed)

- ✅ **Fork Integration**: Automatic FD copying during fork
- ❌ **Cross-Process FD Access**: Not yet implemented
- ❌ **Spawn Tool Integration**: Planned (See [RFC005](/RFC/RFC005_fd_spawn_integration.md))

### 🔄 Phase 2.5: API Enhancements (Planned)

- ❌ **Enhanced read_fd**: Not yet implemented (See [RFC007](/RFC/RFC007_fd_enhanced_api_design.md))
- ❌ **Enhanced fd_to_file**: Not yet implemented (See [RFC007](/RFC/RFC007_fd_enhanced_api_design.md))

### 🔄 Phase 3: Optional Features (Partially Completed)

- ✅ **fd_to_file Tool**: Export FD content to filesystem files
- ❌ **User Input Handling**: Not yet implemented
- ❌ **Reference ID System**: Planned (See [RFC006](/RFC/RFC006_response_reference_id.md))

### Implementation Location

The file descriptor system is implemented in the following files:

- `src/llmproc/tools/file_descriptor.py`: Core implementation of FileDescriptorManager and FD tools
- `src/llmproc/llm_process.py`: Integration with LLMProcess
- `src/llmproc/providers/anthropic_process_executor.py`: Integration with AnthropicProcessExecutor for output wrapping
- `src/llmproc/config/schema.py`: FileDescriptorConfig configuration schema
- `tests/test_file_descriptor.py`: Basic unit tests
- `tests/test_file_descriptor_integration.py`: Integration tests with process model
- `tests/test_fd_to_file_tool.py`: Tests for FD export functionality