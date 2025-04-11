"""Integration tests for token-efficient tool use feature."""

import os
import time
from unittest.mock import patch

import pytest

from llmproc import LLMProgram


@pytest.mark.llm_api
@pytest.mark.extended_api
class TestTokenEfficientToolsIntegration:
    """Integration test suite for token-efficient tool use with actual API calls."""

    @pytest.fixture
    def api_key(self):
        """Get API key from environment variable."""
        return os.environ.get("ANTHROPIC_API_KEY")

    @pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="No Anthropic API key found")
    async def test_token_efficient_tools_integration(self, api_key):
        """Test that token-efficient tools configuration works with actual API calls."""
        if not api_key:
            pytest.skip("No Anthropic API key found")

        # Start timing
        start_time = time.time()

        # Load config with token-efficient tools enabled
        program = LLMProgram.from_toml("examples/features/token-efficient-tools.toml")

        # Start the process
        process = await program.start()

        # Check that extra_headers are in parameters
        assert "extra_headers" in process.api_params
        assert "anthropic-beta" in process.api_params["extra_headers"]
        assert "token-efficient-tools-2025-02-19" in process.api_params["extra_headers"]["anthropic-beta"]

        # Check that calculator tool is enabled
        assert "calculator" in [tool["name"] for tool in process.tools]

        # Run the process with a prompt that should trigger tool use
        result = await process.run("What is the square root of 256? Use the calculator tool.")

        # Check for usage information
        assert result.api_calls > 0
        
        # Verify the correct answer was calculated
        last_message = process.get_last_message()
        assert "16" in last_message, f"Expected calculator result '16' in message: {last_message}"

        # End timing
        end_time = time.time()
        duration = end_time - start_time
        print(f"\nTest completed in {duration:.2f} seconds")
        
        # Verify test completes within reasonable time
        assert duration < 20.0, f"Test took too long: {duration:.2f}s"