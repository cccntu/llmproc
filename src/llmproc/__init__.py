"""LLMProc - A simple framework for LLM-powered applications."""

from llmproc.program import LLMProgram  # Need to import LLMProgram first to avoid circular import
from llmproc.llm_process import LLMProcess

__all__ = ["LLMProcess", "LLMProgram"]
__version__ = "0.1.0"
