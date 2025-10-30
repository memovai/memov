"""
Summarizer module for generating AI-powered summaries using OpenAI API
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv

    DOTENV_AVAILABLE = True
    # Load .env files in priority order
    load_dotenv(".env.local")  # Local overrides (not in git)
    load_dotenv(".env")  # Default env file
except ImportError:
    DOTENV_AVAILABLE = False

LOGGER = logging.getLogger(__name__)


class HTTPOpenAISummarizer:
    """
    HTTP-based OpenAI summarizer that doesn't depend on the openai package
    """

    def __init__(self, api_key: str = None, model: str = "qwen2:0.5b"):
        """
        Initialize the HTTP OpenAI summarizer

        Args:
            api_key: OpenAI API key (will use OPENAI_API_KEY env var if not provided)
            model: OpenAI model to use for summarization
        """
        # Try to reload .env files each time (for MCP server context)
        if DOTENV_AVAILABLE:
            try:
                from dotenv import load_dotenv

                load_dotenv(".env.local", override=True)
                load_dotenv(".env", override=True)
                LOGGER.info("Reloaded .env files")
            except Exception as e:
                LOGGER.warning(f"Failed to reload .env files: {e}")

        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.api_url = "http://127.0.0.1:11434/v1/chat/completions"
        # self.api_url = "https://api.openai.com/v1/chat/completions"

        LOGGER.info(f"API key set: {'Yes' if self.api_key else 'No'}")

    def is_available(self) -> bool:
        """Check if the summarizer is ready to use"""
        return bool(self.api_key)

    def generate_summary(self, context: str) -> str:
        """
        Generate a detailed summary from the provided context using OpenAI API via HTTP

        Args:
            context: The commit history and context to summarize

        Returns:
            Generated summary text
        """
        if not self.is_available():
            return f"❌ OpenAI API key not found. Please set OPENAI_API_KEY in .env or .env.local file.\n💡 Current working directory: {os.getcwd()}\n💡 Checked environment variable: {bool(os.environ.get('OPENAI_API_KEY'))}"

        try:
            # Prepare the request data using standard chat completions with JSON mode
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self._get_json_system_prompt()},
                    {
                        "role": "user",
                        "content": f"Analyze and summarize the following commit history and context:\n\n{context}",
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 4000,
            }

            # Convert to JSON
            json_data = json.dumps(data).encode("utf-8")

            # Create the HTTP request
            req = urllib.request.Request(
                self.api_url,
                data=json_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )

            # Make the request
            with urllib.request.urlopen(req, timeout=60) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            if "choices" in response_data and len(response_data["choices"]) > 0:
                # The content should already be structured JSON
                content = response_data["choices"][0]["message"]["content"]
                # Try to parse and reformat the JSON to ensure it's valid
                try:
                    parsed_json = json.loads(content)
                    return json.dumps(parsed_json, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    # If not valid JSON, return as is
                    return content
            else:
                return f"❌ Unexpected response format: {response_data}"

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else "No error details"
            LOGGER.error(f"HTTP Error calling OpenAI API: {e.code} - {error_body}")
            return f"❌ HTTP Error {e.code}: {error_body}"
        except Exception as e:
            LOGGER.error(f"Error calling OpenAI API: {e}", exc_info=True)
            return f"❌ Error generating AI summary: {str(e)}"

    def _get_json_system_prompt(self) -> str:
        """Get optimized system prompt that ensures JSON output"""
        return f"""You are an expert development assistant specializing in analyzing commit history and creating detailed project summaries.

You must respond with a valid JSON object following this exact schema:

{json.dumps(self._get_output_schema(), indent=2)}

Instructions for analysis:
1. Analyze each commit chronologically
2. Extract user requests and intents behind changes
3. Identify technical decisions and code patterns
4. Document file changes with specific details
5. Note errors encountered and how they were resolved
6. Track ongoing troubleshooting efforts

Focus on:
- Full code snippets where applicable
- Function signatures and architectural decisions
- Test outputs and code changes
- User feedback and changing requirements
- Specific file names and their importance

Create comprehensive analysis that allows another developer to understand full context and continue work seamlessly.

IMPORTANT: Your response must be valid JSON only, no additional text or formatting."""

    def _get_optimized_instructions(self) -> str:
        """Get optimized instructions for the new responses API"""
        return """You are an expert development assistant specializing in analyzing commit history and creating detailed project summaries. Your task is to analyze the provided commit context and create a structured summary that captures all essential information for continuing development work.

Focus on:
1. Chronological analysis of each commit
2. User requests and intents behind each change
3. Technical decisions and code patterns
4. File changes with specific details
5. Errors encountered and how they were resolved
6. Ongoing troubleshooting efforts

Pay special attention to:
- Full code snippets where applicable
- Function signatures and architectural decisions
- Test outputs and code changes
- User feedback and changing requirements
- Specific file names and their importance

Create a comprehensive analysis that would allow another developer to understand the full context and continue the work seamlessly."""

    def _get_output_schema(self) -> dict:
        """Define the structured output schema for the summary"""
        return {
            "type": "object",
            "properties": {
                "primary_request_and_intent": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "All user explicit requests and intents in detail",
                },
                "key_technical_concepts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Important technical concepts, technologies, and frameworks",
                },
                "files_and_code_sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_name": {"type": "string"},
                            "importance": {"type": "string"},
                            "changes_made": {"type": "string"},
                            "code_snippet": {"type": "string"},
                        },
                    },
                    "description": "Files examined, modified, or created with code details",
                },
                "errors_and_fixes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "error_description": {"type": "string"},
                            "fix_applied": {"type": "string"},
                            "user_feedback": {"type": "string"},
                        },
                    },
                    "description": "Errors encountered and how they were resolved",
                },
                "problem_solving": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Problems solved and ongoing troubleshooting efforts",
                },
                "all_user_messages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "All non-tool user messages for understanding feedback",
                },
                "pending_tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tasks explicitly asked to work on",
                },
                "current_work": {
                    "type": "string",
                    "description": "Precise description of work being done before this summary",
                },
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recommended next steps based on explicit user requests",
                },
            },
            "required": [
                "primary_request_and_intent",
                "key_technical_concepts",
                "files_and_code_sections",
                "errors_and_fixes",
                "problem_solving",
                "current_work",
            ],
        }

    def _get_system_prompt(self) -> str:
        """Get the detailed system prompt for summarization"""
        return """Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions. This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing development work without losing context.

Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and ensure you've covered all necessary points. In your analysis process:
1. Chronologically analyze each message and section of the conversation. For each section thoroughly identify:
   - The user's explicit requests and intents
   - Your approach to addressing the user's requests
   - Key decisions, technical concepts and code patterns
   - Specific details like:
     - file names
     - full code snippets
     - function signatures
     - file edits
   - Errors that you ran into and how you fixed them
   - Pay special attention to specific user feedback that you received, especially if the user told you to do something differently.
2. Double-check for technical accuracy and completeness, addressing each required element thoroughly.

Your summary should include the following sections:
1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail
2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. Pay special attention to the most recent messages and include full code snippets where applicable and include a summary of why this file read or edit is important.
4. Errors and fixes: List all errors that you ran into, and how you fixed them. Pay special attention to specific user feedback that you received, especially if the user told you to do something differently.
5. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.
6. All user messages: List ALL user messages that are not tool results. These are critical for understanding the users' feedback and changing intent.
7. Pending Tasks: Outline any pending tasks that you have explicitly been asked to work on.
8. Current Work: Describe in detail precisely what was being worked on immediately before this summary request, paying special attention to the most recent messages from both user and assistant. Include file names and code snippets where applicable.
9. Optional Next Step: List the next step that you will take that is related to the most recent work you were doing. IMPORTANT: ensure that this step is DIRECTLY in line with the user's explicit requests, and the task you were working on immediately before this summary request. If your last task was concluded, then only list next steps if they are explicitly in line with the users request. Do not start on tangential requests without confirming with the user first.

## Compact Instructions
When summarizing the conversation focus on typescript code changes and also remember the mistakes you made and how you fixed them.

# Summary instructions
When you are using compact - please focus on test output and code changes. Include file reads verbatim."""


def create_summary_from_commits(
    commit_details: List[Dict[str, Any]], use_ai: bool = True
) -> Dict[str, Any]:
    """
    Create a comprehensive summary from commit details

    Args:
        commit_details: List of commit information dictionaries
        use_ai: Whether to use AI summarization (requires OpenAI API key)

    Returns:
        Dictionary containing the generated summary
    """
    # Create context string by concatenating all commit details
    context_parts = []
    for i, commit in enumerate(commit_details, 1):
        context_parts.append(f"=== Commit {i}: {commit.get('commit_hash', 'unknown')} ===")
        context_parts.append(f"Summary: {commit.get('summary_line', 'No summary')}")
        context_parts.append(f"Details:\n{commit.get('details', 'No details available')}")
        context_parts.append("")  # Empty line separator

    context = "\n".join(context_parts)

    if use_ai:
        # Try AI summarization using HTTP client (no dependencies)
        summarizer = HTTPOpenAISummarizer()
        ai_summary = summarizer.generate_summary(context)
        print("AI Summary Generated:")
        print(ai_summary)

        return {
            "ai_generated_summary": ai_summary,
            "metadata": {
                "commits_analyzed": len(commit_details),
                "commit_hashes": [
                    commit.get("commit_hash", "unknown") for commit in commit_details
                ],
                "generation_method": (
                    "http_openai_api"
                    if summarizer.is_available() and not ai_summary.startswith("❌")
                    else "fallback"
                ),
            },
            "raw_context": context,
        }
    else:
        # Fallback to basic analysis
        return {
            "basic_summary": f"Analyzed {len(commit_details)} commits",
            "metadata": {
                "commits_analyzed": len(commit_details),
                "commit_hashes": [
                    commit.get("commit_hash", "unknown") for commit in commit_details
                ],
                "generation_method": "basic",
            },
            "raw_context": context,
        }
