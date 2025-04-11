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
max_direct_output_chars = 8000      # Threshold for FD creation
default_page_size = 4000            # Size of each page
max_input_chars = 8000              # Threshold for user input FD creation
page_user_input = true              # Enable/disable user input paging
enable_references = true            # Enable the reference ID system
```

**Note**: The system is enabled if any FD tool is in `[tools].enabled` OR `enabled = true` exists in the `[file_descriptor]` section.

## Usage

### Basic File Descriptor Operations

```python
# Basic Operations
read_fd(fd="fd:1", start=2)                # Read page 2
read_fd(fd="fd:1", read_all=True)          # Read the entire content
fd_to_file(fd="fd:1", file_path="/path/to/output.txt")  # Export to file

# Enhanced operations
# Extract content to a new file descriptor
new_fd = read_fd(fd="fd:1", start=2, extract_to_new_fd=True)  # Returns new FD like "fd:2"

# Read specific lines (Enhanced API)
content = read_fd(fd="fd:1", mode="line", start=10, count=5)  # Read lines 10-14

# Read character ranges (Enhanced API)
content = read_fd(fd="fd:1", mode="char", start=100, count=200)  # Read 200 chars

# Append to existing file (Enhanced API)
fd_to_file(fd="fd:1", file_path="/path/to/output.txt", mode="append")

# Control file creation behavior (Enhanced API)
fd_to_file(fd="fd:1", file_path="/path/to/output.txt", exist_ok=False)  # Don't overwrite
fd_to_file(fd="fd:1", file_path="/path/to/output.txt", create=False)    # Update only
```

### Reference ID System

The reference ID system allows the LLM to mark up content in its responses for later reference:

```
Here's a code snippet I want to reference later:

<ref id="example_code">
def hello_world():
    print("Hello, world!")
</ref>

You can use the reference later by accessing it with read_fd(fd="ref:example_code").
```

References are automatically created as file descriptors with the prefix `ref:` followed by the ID. 
They can be accessed using the standard `read_fd` tool just like any other file descriptor.

### Spawn and Fork Integration

References are automatically shared between processes during fork and spawn operations:

1. When forking a process, all references from the parent are copied to the child.
2. When spawning a child process, all references from the parent are automatically shared.
3. References created in child processes remain isolated and are not visible to the parent.

This enables complex workflows where multiple processes can share marked-up content without
explicitly passing file descriptors.

```python
# Parent process creates a reference
<ref id="important_data">Data the child will need</ref>

# Child process can access the reference automatically
spawn(program_name="analyzer", query="Analyze the content in ref:important_data")

# Inside the child process
read_fd(fd="ref:important_data")  # Works automatically
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
- **Reference ID System**: Mark up content with reference IDs for later access
- **Reference Inheritance**: References automatically shared during fork/spawn operations

## Implementation

The file descriptor system is implemented in the `src/llmproc/file_descriptors/` package with these key components:

1. **FileDescriptorManager**: Core class managing creation and access
2. **read_fd Tool**: System call interface for accessing content
3. **fd_to_file Tool**: System call interface for exporting content to files
4. **XML Formatting**: Standard response format with metadata
5. **Reference Extraction**: System for extracting and managing reference IDs

### Integration

The file descriptor system integrates with:

- **LLMProcess**: Initializes and maintains FD manager state
- **AnthropicProcessExecutor**: Automatically wraps large outputs
- **fork_process**: Maintains FD state during process forking
- **spawn_tool**: Shares references between parent and child processes

### Performance Optimizations

The file descriptor system includes several performance optimizations:

- **Reference Extraction**: O(n log n) algorithm for detecting nested references
- **Compiled Regex**: Pre-compiled regex patterns for faster reference extraction
- **Proper Pagination**: Uses the calculate_total_pages function for consistent pagination
- **Efficient XML Formatting**: Streamlined XML generation for standard outputs
- **Memory Efficiency**: File descriptors are copied by reference where possible

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

### ✅ Phase 2: Process Integration (Completed)

- ✅ **Fork Integration**: Automatic FD copying during fork
- ✅ **Cross-Process FD Access**: Implemented via reference inheritance
- ✅ **Spawn Tool Integration**: Implemented (See [RFC005](/RFC/RFC005_fd_spawn_integration.md))

### ✅ Phase 2.5: API Enhancements (Completed)

- ✅ **Enhanced read_fd**: Implemented with extract_to_new_fd and positioning modes (See [RFC007](/RFC/RFC007_fd_enhanced_api_design.md))
- ✅ **Enhanced fd_to_file**: Implemented with mode, create, and exist_ok parameters (See [RFC007](/RFC/RFC007_fd_enhanced_api_design.md))

### 🔄 Phase 3: Optional Features (Partially Completed)

- ✅ **fd_to_file Tool**: Export FD content to filesystem files
- 🔄 **User Input Handling**: Partially implemented (basic user input paging)
- ✅ **Reference ID System**: Implemented (See [RFC006](/RFC/RFC006_response_reference_id.md))

### Implementation Location

The file descriptor system is implemented in the following files:

- `src/llmproc/file_descriptors/`: Package containing all file descriptor functionality
  - `manager.py`: Core implementation of FileDescriptorManager
  - `fd_tools.py`: Implementation of read_fd and fd_to_file tools (in builtin/fd_tools.py)
  - `references.py`: Reference ID system implementation (optimized for performance)
  - `paginator.py`: Line-aware content pagination
  - `formatter.py`: XML formatting utilities
  - `constants.py`: Shared constants and definitions
- `src/llmproc/llm_process.py`: Integration with LLMProcess
- `src/llmproc/providers/anthropic_process_executor.py`: Integration with AnthropicProcessExecutor for output wrapping
- `src/llmproc/tools/spawn.py`: Integration with spawn system call for reference inheritance
- `src/llmproc/config/schema.py`: FileDescriptorConfig configuration schema
- Tests:
  - `tests/test_file_descriptor.py`: Basic unit tests
  - `tests/test_file_descriptor_integration.py`: Integration tests with process model
  - `tests/test_fd_to_file_tool.py`: Tests for FD export functionality
  - `tests/test_reference_system.py`: Tests for reference ID system
  - `tests/test_fd_spawn_integration.py`: Tests for spawn integration
  - `tests/test_fd_all_features.py`: Tests for all FD features combined
