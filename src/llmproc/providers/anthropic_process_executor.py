"""Anthropic provider tools implementation for LLMProc."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import asyncio
import logging

logger = logging.getLogger(__name__)


PROMPT_FORCE_MODEL_RESPONSE = "Please respond with a text response"
PROMPT_SUMMARIZE_CONVERSATION = "Please stop using tools and summarize your progress so far"

class AnthropicProcessExecutor:
    async def run(self, process: 'Process', user_prompt: str, max_iterations: int = 10, 
                  callbacks: dict = None, run_result = None, is_tool_continuation: bool = False) -> int:
        """Execute a conversation with the Anthropic API.
        
        Args:
            process: The LLMProcess instance
            user_prompt: The user's input message
            max_iterations: Maximum number of API calls for tool usage
            callbacks: Optional dictionary of callback functions
            run_result: Optional RunResult object to track execution metrics
            is_tool_continuation: Whether this is continuing a previous tool call
            
        Returns:
            int: The number of iterations (api calls) used
        """
        # Initialize callbacks
        callbacks = callbacks or {}
        on_tool_start = callbacks.get('on_tool_start')
        on_tool_end = callbacks.get('on_tool_end')
        on_response = callbacks.get('on_response')
        
        if is_tool_continuation:
            pass
        else:
            process.messages.append({"role": "user", "content": user_prompt})

        process.run_stop_reason = None
        iterations = 0
        while iterations < max_iterations:

            iterations += 1
            
            logger.debug(f"Making API call {iterations}/{max_iterations}")
            
            # Make the API call
            response = await process.client.messages.create(
                model=process.model_name,
                system=process.enriched_system_prompt,
                messages=[message for message in process.messages if message["role"] != "system"],
                tools=process.tools,
                **process.api_params
            )
            
            # Track API call in the run result if available
            if run_result:
                # Extract API usage information
                api_info = {
                    "model": process.model_name,
                    "usage": getattr(response, "usage", {}),
                    "stop_reason": getattr(response, "stop_reason", None),
                    "id": getattr(response, "id", None),
                }
                run_result.add_api_call(api_info)

            stop_reason = response.stop_reason

            has_tool_calls = len([content for content in response.content if content.type == "tool_use"]) > 0
            tool_results = []
            # NOTE: these are the possible stop_reason values: ["end_turn", "max_tokens", "stop_sequence"]:
            process.stop_reason = stop_reason # TODO: not finalized api,
            if not has_tool_calls:
                if response.content:
                    # NOTE: sometimes model can decide to not response any text, for example, after using tools.
                    # appending the empty assistant message will cause the following API error in the next api call:
                    # ERROR: all messages must have non-empty content except for the optional final assistant message
                    process.state.append({"role": "assistant", "content": response.content})
                # NOTE: this is needed for user to check the stop reason afterward
                process.run_stop_reason = stop_reason
                break
            else:
                # Fire callback for model response if provided
                if on_response and 'on_response' in callbacks:
                    # Extract text content for callback
                    text_content = ""
                    for c in response.content:
                        if hasattr(c, "type") and c.type == "text" and hasattr(c, "text"):
                            text_content += c.text
                    try:
                        on_response(text_content)
                    except Exception as e:
                        logger.warning(f"Error in on_response callback: {str(e)}")
                
                for content in response.content:
                    if content.type == "text":
                        continue
                        # NOTE: right now the text response will be appended to messages list later
                    elif content.type == "tool_use":
                        tool_name = content.name
                        tool_args = content.input
                        tool_id = content.id
                        
                        # Fire callback for tool start if provided
                        if on_tool_start:
                            try:
                                on_tool_start(tool_name, tool_args)
                            except Exception as e:
                                logger.warning(f"Error in on_tool_start callback: {str(e)}")

                        # Track tool in run_result if available
                        if run_result:
                            run_result.add_api_call({
                                "type": "tool_call",
                                "tool_name": tool_name,
                            })

                        # NOTE: fork requires special handling, such as removing all other tool calls from the last assistant response
                        # so we separate the fork handling from other tool call handling
                        if tool_name == "fork":
                            logger.info(f"Forking with tool_args: {tool_args}")
                            result = await self._fork(
                                process, tool_args, tool_id, last_assistant_response=response.content
                            )
                        else:
                            result = await process.call_tool(tool_name, tool_args)
                            
                        # Fire callback for tool end if provided
                        if on_tool_end:
                            try:
                                on_tool_end(tool_name, result)
                            except Exception as e:
                                logger.warning(f"Error in on_tool_end callback: {str(e)}")
                                
                        tool_results.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": result,
                                }
                            ],
                        })
                process.messages.append({"role": "assistant", "content": response.content})
                process.messages.extend(tool_results)
        if iterations >= max_iterations:
            process.run_stop_reason = "max_iterations"
        return iterations

    async def run_till_text_response(self, process, user_prompt, max_iterations: int = 10):
        """
        Run the process until a text response is generated
        This is specifically designed for forked processes, where the child must respond with a text response, which will become the tool result for the parent.

        This has some special handling, it's not meant for general use.
        """
        iterations = 0
        next_prompt = user_prompt
        callbacks = {}  # No callbacks for this internal method
        total_api_calls = 0
        
        while iterations < max_iterations:
            # Run the process and get a RunResult
            run_result = await self.run(process, next_prompt, max_iterations=max_iterations-iterations, 
                                       callbacks=callbacks, is_tool_continuation=False)
            
            # Track API calls
            iterations += run_result.api_calls 
            total_api_calls += run_result.api_calls
            
            # Check if we've reached the text response we need
            last_message = process.get_last_message()
            if last_message:
                return last_message  # Return the text message directly
                
            # If we didn't get a response, handle special cases
            if process.run_stop_reason == "max_iterations":
                # Allow the model another chance to respond with a text response to summarize
                run_result = await self.run(process, PROMPT_SUMMARIZE_CONVERSATION, 
                                           max_iterations=1, callbacks=callbacks, 
                                           is_tool_continuation=False)
                total_api_calls += run_result.api_calls
                
                # Check again for a text response
                last_message = process.get_last_message()
                if last_message:
                    return last_message

            # If we still don't have a text response, prompt again
            next_prompt = PROMPT_FORCE_MODEL_RESPONSE
        
        # If we've exhausted iterations without getting a proper response
        return "Maximum iterations reached without final response."


    @staticmethod
    async def _fork(process, params, tool_id, last_assistant_response):
        """Fork a conversation"""
        if not process.allow_fork:
            return "Forking is not allowed for this agent, possible reason: You are already a forked instance"

        prompts = params["prompts"]
        print(f"Forking conversation with {len(prompts)} prompts: {prompts}")

        async def process_fork(i, prompt):
            child = process.deepcopy() # TODO: need to implement deepcopy for Process class

            # NOTE: we need to remove all other tool calls from the last assistant response
            # because we might not have the tool call results for other tool calls yet
            # this is also important for the forked process to focus on the assigned goal
            child.messages.append(
                {
                    "role": "assistant",
                    "content": [
                        content
                        for content in last_assistant_response
                        if content.type != "tool_use"
                        or (content.type == "tool_use" and content.id == tool_id)
                    ],
                }
            )
            # NOTE: return the fork result as tool result
            child.messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": "pid==0, you are a child instance produced from a fork. you are not allowed to use the fork tool. please continue the conversation with only the assigned goal",
                        }
                    ],
                }
            )
            # NOTE: run() will immediately add the prompt to the conversation as user message
            # I found this to work better than adding the prompt as the tool result
            executor = AnthropicProcessExecutor()  # Create a new executor for the child
            response = await executor.run_till_text_response(
                child, user_prompt=prompt, max_iterations=20
            )
            return {"id": i, "message": response}

        # Process all forks in parallel
        responses = await asyncio.gather(
            *[process_fork(i, prompt) for i, prompt in enumerate(prompts)]
        )
        result = json.dumps(responses)
        return result



