"""
LLM client for document generation.

Provides a unified interface for calling various LLM providers.
Uses litellm for multi-provider support.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with LLM APIs."""

    def __init__(self, models: List[str], api_key: Optional[str] = None):
        """
        Initialize LLM client.

        Args:
            models: List of model names to use
            api_key: Optional API key (will use environment variables if not provided)
        """
        self.models = models
        self.api_key = api_key

        # Try to import litellm
        try:
            import litellm
            self.litellm = litellm
            self.available = True

            # Configure litellm
            if api_key:
                litellm.api_key = api_key

            # Suppress verbose logging
            litellm.set_verbose = False

        except ImportError:
            logger.warning(
                "litellm not installed. Install with: pip install litellm\n"
                "Document generation will use fallback mode."
            )
            self.litellm = None
            self.available = False

    def query_single(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Query a single LLM model.

        Args:
            model: Model name
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments for litellm

        Returns:
            Dictionary with 'content' and optionally 'error' keys
        """
        if not self.available or not self.litellm:
            return {
                'error': 'LLM client not available',
                'content': ''
            }

        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            messages.append({
                "role": "user",
                "content": prompt
            })

            # Call LLM
            response = self.litellm.completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            print("LLM Response:", response)

            # Extract content
            content = response.choices[0].message.content

            return {
                'content': content,
                'model': model,
                # Unused now
                # 'usage': response.usage._asdict() if hasattr(response, 'usage') else {}
                'usage': response.usage
            }

        except Exception as e:
            logger.error(f"Error calling LLM {model}: {e}")
            return {
                'error': str(e),
                'content': ''
            }

    def query_multiple(
        self,
        prompts: List[str],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Query LLM with multiple prompts.

        Args:
            prompts: List of prompts
            model: Model to use (default: first model in list)
            system_prompt: Optional system prompt
            **kwargs: Additional arguments

        Returns:
            List of response dictionaries
        """
        if not model:
            model = self.models[0] if self.models else "gpt-4o-mini"

        responses = []
        for prompt in prompts:
            response = self.query_single(
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                **kwargs
            )
            responses.append(response)

        return responses
