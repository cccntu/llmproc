#!/usr/bin/env python3
"""Command-line interface for LLMProc - Demo version.

This module provides the main CLI functionality for the llmproc-demo command.
"""

import asyncio
import logging
import sys
import time
import tomllib
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from llmproc import LLMProgram
from llmproc.callbacks import CallbackEvent
from llmproc.common.results import RunResult
from llmproc.providers.constants import ANTHROPIC_PROVIDERS

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("llmproc.cli")


def get_logger(quiet=False):
    """Get a logger with the appropriate level based on quiet mode."""
    if quiet:
        # Set llmproc.cli logger to ERROR level in quiet mode
        logger.setLevel(logging.ERROR)

        # Also reduce logging from httpx and llmproc modules
        logging.getLogger("httpx").setLevel(logging.ERROR)
        logging.getLogger("llmproc.llm_process").setLevel(logging.ERROR)

        # Suppress Pydantic warnings
        import warnings

        warnings.filterwarnings("ignore", module="pydantic")
    return logger


def run_with_prompt(
    process: Any, user_prompt: str, source: str, logger: logging.Logger, callback_handler: Any, quiet: bool
) -> RunResult:
    """Run a single prompt with the given process.

    Args:
        process: The LLMProcess to run the prompt with
        user_prompt: The prompt text to run
        source: Description of where the prompt came from
        logger: Logger for diagnostic messages
        callback_handler: Callback instance to register with the process
        quiet: Whether to run in quiet mode

    Returns:
        RunResult with the execution results
    """
    # Report mode
    logger.info(f"Running with {source} prompt")

    # Track time for this run
    start_time = time.time()

    # Run the process with the prompt, using the process's max_iterations
    run_result = asyncio.run(process.run(user_prompt, max_iterations=process.max_iterations))

    # Get the elapsed time
    elapsed = time.time() - start_time

    # Log run result information
    logger.info(f"Used {run_result.api_calls} API calls and {run_result.tool_calls} tool calls in {elapsed:.2f}s")

    # Get the last assistant message and print the response
    response = process.get_last_message()
    click.echo(response)

    return run_result


def check_and_run_demo_mode(
    program: LLMProgram, run_prompt_func: callable, quiet: bool, logger: logging.Logger
) -> bool:
    """Check if program has demo mode configured and run it if available.

    Args:
        program: The LLMProgram to check for demo configuration
        run_prompt_func: Function to run individual prompts
        quiet: Whether to run in quiet mode
        logger: Logger for diagnostic messages

    Returns:
        True if demo mode was found and executed, False otherwise
    """
    if not hasattr(program, "source_path") or not program.source_path:
        return False

    from llmproc.config.schema import DemoConfig

    # Read the original TOML file to check for demo section
    try:
        with open(program.source_path, "rb") as f:
            config_data = tomllib.load(f)

        if "demo" in config_data and "prompts" in config_data["demo"] and config_data["demo"]["prompts"]:
            # Get demo configuration
            demo_prompts = config_data["demo"]["prompts"]
            pause_between = config_data["demo"].get("pause_between_prompts", True)
            # If there's a display_name in the demo section, use it
            if "display_name" in config_data["demo"]:
                process.display_name = config_data["demo"]["display_name"]

            # Define demo mode function
            def run_demo_mode(prompts: list[str], pause: bool = True) -> bool:
                """Run a series of prompts in demo mode."""
                logger.info(f"Starting demo mode with {len(prompts)} prompts")

                # Prepare the demo
                if not quiet:
                    click.echo("\n===== Demo Mode =====")
                    click.echo(f"Running {len(prompts)} prompts in sequence")
                    if pause:
                        click.echo("Press Enter after each response to continue to the next prompt")
                    click.echo("====================\n")

                # Run each prompt in sequence
                for i, prompt in enumerate(prompts):
                    # Show prompt number and content
                    if not quiet:
                        click.echo(f"\n----- Prompt {i + 1}/{len(prompts)} -----")
                        click.echo(f"User: {prompt}")

                    # Run the prompt
                    run_prompt_func(prompt, source=f"demo prompt {i + 1}/{len(prompts)}")

                    # Pause for user input if configured, except after the last prompt
                    if pause and i < len(prompts) - 1:
                        click.echo("\nPress Enter to continue to the next prompt...", nl=False)
                        input()

                if not quiet:
                    click.echo("\n===== Demo Complete =====")

                return True

            # Run in demo mode
            return run_demo_mode(demo_prompts, pause=pause_between)

    except Exception as e:
        logger.warning(f"Failed to check for demo configuration: {str(e)}")

    return False


@click.command()
@click.argument("program_path", required=True)
@click.option("--prompt", "-p", help="Run in non-interactive mode with the given prompt")
@click.option(
    "--non-interactive",
    "-n",
    is_flag=True,
    help="Run in non-interactive mode (reads from stdin if no prompt provided)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Reduce logging output and callbacks",
)
def main(program_path, prompt=None, non_interactive=False, quiet=False) -> None:
    """Run a simple CLI for LLMProc.

    PROGRAM_PATH is the path to a TOML program file.

    Supports three modes:
    1. Interactive mode (default): Chat continuously with the model
    2. Non-interactive with prompt: Use --prompt/-p "your prompt here"
    3. Non-interactive with stdin: Use --non-interactive/-n and pipe input
    """
    # Only show header in interactive mode or if verbose logging is enabled
    if not (prompt or non_interactive) or logging.getLogger("llmproc").level == logging.DEBUG:
        click.echo("LLMProc CLI Demo")
        click.echo("----------------")

    # Validate program path
    program_file = Path(program_path)
    if not program_file.exists():
        click.echo(f"Error: Program file not found: {program_path}")
        sys.exit(1)
    if program_file.suffix != ".toml":
        click.echo(f"Error: Program file must be a TOML file: {program_path}")
        sys.exit(1)
    selected_program = program_file

    # Load the selected program
    try:
        selected_program_abs = selected_program.absolute()

        # Get logger with appropriate level
        cli_logger = get_logger(quiet)

        # Use the new API: load program first, then start it asynchronously
        cli_logger.info(f"Loading program from: {selected_program_abs}")
        program = LLMProgram.from_toml(selected_program_abs)

        # Display program summary unless in quiet mode
        if not quiet:
            click.echo("\nProgram Summary:")
            click.echo(f"  Model: {program.model_name}")
            click.echo(f"  Provider: {program.provider}")
            click.echo(f"  Display Name: {program.display_name or program.model_name}")

        # Initial token count will be displayed after initialization

        # Show brief system prompt summary unless in quiet mode
        if not quiet and hasattr(program, "system_prompt") and program.system_prompt:
            system_prompt = program.system_prompt
            # Truncate if too long
            if len(system_prompt) > 60:
                system_prompt = system_prompt[:57] + "..."
            click.echo(f"  System Prompt: {system_prompt}")

        # Show parameter summary if available and not in quiet mode
        if not quiet and hasattr(program, "api_params") and program.api_params:
            params = program.api_params
            if "temperature" in params:
                click.echo(f"  Temperature: {params['temperature']}")
            if "max_tokens" in params:
                click.echo(f"  Max Tokens: {params['max_tokens']}")

        # Initialize the process asynchronously
        cli_logger.info("Starting process initialization...")
        start_time = time.time()
        process = asyncio.run(program.start())
        init_time = time.time() - start_time
        cli_logger.info(f"Process initialized in {init_time:.2f} seconds")

        # Create callback class for real-time updates
        class CliCallbackHandler:
            def tool_start(self, tool_name, args):
                if not quiet:
                    cli_logger.info(f"Using tool: {tool_name}")
                
            def tool_end(self, tool_name, result):
                if not quiet:
                    cli_logger.info(f"Tool {tool_name} completed")
                
            def response(self, content):
                if not quiet:
                    cli_logger.info(f"Received response: {content[:50]}...")
        
        # Create callback handler and register it with the process
        callback_handler = CliCallbackHandler()
        process.add_callback(callback_handler)

        # Use the helper function to run prompts
        run_prompt_func = lambda user_prompt, source="command line": run_with_prompt(
            process, user_prompt, source, cli_logger, callback_handler, quiet
        )

        # Priority order for prompts/modes:
        # 1. Command-line prompt (-p flag)
        # 2. stdin (if non-interactive flag)
        # 3. Demo mode (if configured)
        # 4. User prompt from TOML
        # 5. Interactive mode

        if prompt is not None:
            # Run with command-line prompt
            if prompt.strip() == "":
                click.echo(
                    "Error: Empty prompt provided. Please provide a non-empty prompt with --prompt.",
                    err=True,
                )
                sys.exit(1)
            run_prompt_func(prompt, source="command line")

        elif non_interactive:
            # Non-interactive mode with stdin
            if not sys.stdin.isatty():  # Check if input is being piped in
                stdin_prompt = sys.stdin.read().strip()
                if stdin_prompt.strip() == "":
                    click.echo(
                        "Error: Empty prompt provided via stdin.",
                        err=True,
                    )
                    sys.exit(1)
                run_prompt_func(stdin_prompt, source="stdin")
            else:
                click.echo(
                    "Error: No prompt provided for non-interactive mode. Use --prompt or pipe input.",
                    err=True,
                )
                sys.exit(1)

        # Check for demo mode configuration in the program's TOML
        elif check_and_run_demo_mode(program, run_prompt_func, quiet, cli_logger):
            return  # Exit after demo is complete

        elif hasattr(process, "user_prompt") and process.user_prompt:
            # Run with embedded user prompt from TOML
            run_prompt_func(process.user_prompt, source="embedded")

        else:
            # Interactive mode
            if not quiet:
                click.echo("\nStarting interactive chat session. Type 'exit' or 'quit' to end.")

            # Show initial token count for Anthropic models (unless in quiet mode)
            if not quiet and process.provider in ANTHROPIC_PROVIDERS:
                try:
                    token_info = asyncio.run(process.count_tokens())
                    if token_info and "input_tokens" in token_info:
                        click.echo(
                            f"Initial context size: {token_info['input_tokens']:,} tokens ({token_info['percentage']:.1f}% of {token_info['context_window']:,} token context window)"
                        )
                except Exception as e:
                    cli_logger.warning(f"Failed to count initial tokens: {str(e)}")

            while True:
                # Display token usage if available from the count_tokens method (unless in quiet mode)
                token_display = ""
                if not quiet and process.provider in ANTHROPIC_PROVIDERS:
                    try:
                        token_info = asyncio.run(process.count_tokens())
                        if token_info and "input_tokens" in token_info:
                            token_display = (
                                f" [Tokens: {token_info['input_tokens']:,}/{token_info['context_window']:,}]"
                            )
                    except Exception as e:
                        cli_logger.warning(f"Failed to count tokens for prompt: {str(e)}")

                user_input = click.prompt(f"\nYou{token_display}", prompt_suffix="> ")

                if user_input.lower() in ("exit", "quit"):
                    if not quiet:
                        click.echo("Ending session.")
                    break

                # Track time for this run
                start_time = time.time()

                # Show a spinner while running (unless in quiet mode)
                if not quiet:
                    click.echo("Thinking...", nl=False)

                # Run the process without passing callbacks (already registered above)
                run_result = asyncio.run(process.run(user_input))

                # Get the elapsed time
                elapsed = time.time() - start_time

                # Clear the "Thinking..." text (unless in quiet mode)
                if not quiet:
                    click.echo("\r" + " " * 12 + "\r", nl=False)

                # Token counting is now handled before each prompt using the count_tokens method

                # Log basic info
                if run_result.api_calls > 0:
                    cli_logger.info(
                        f"Used {run_result.api_calls} API calls and {run_result.tool_calls} tool calls in {elapsed:.2f}s"
                    )

                # Get the last assistant message
                response = process.get_last_message()

                # Display the response (with or without model name based on quiet mode)
                if quiet:
                    click.echo(f"\n{response}")
                else:
                    display_name = process.display_name or process.model_name
                    click.echo(f"\n{display_name}> {response}")

                # Display token usage stats if available (unless in quiet mode)
                if not quiet and hasattr(run_result, "total_tokens") and run_result.total_tokens > 0:
                    click.echo(
                        f"[API calls: {run_result.api_calls}, "
                        f"Tool calls: {run_result.tool_calls}, "
                        f"Tokens: {run_result.input_tokens}/{run_result.output_tokens}/{run_result.total_tokens} (in/out/total)]"
                    )

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        # Only show full traceback if not in quiet mode
        if not quiet:
            click.echo("\nFull traceback:", err=True)
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
