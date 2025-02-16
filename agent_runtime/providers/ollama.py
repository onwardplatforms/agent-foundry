# agent_runtime/providers/ollama.py
"""Ollama provider implementation."""

import json
from typing import AsyncIterator, Optional, Dict, Any

import aiohttp
import requests
from requests.exceptions import RequestException
from semantic_kernel.contents import (
    AuthorRole,
    ChatHistory,
    StreamingChatMessageContent,
)
from semantic_kernel.kernel import Kernel

from agent_runtime.env import get_env_var
from agent_runtime.providers.base import OllamaSettings, Provider, ProviderConfig


class OllamaProvider(Provider):
    """Ollama provider implementation that does not do function calling."""

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize provider."""
        # Get model and base URL from environment variables
        env_model = get_env_var("OLLAMA_MODEL", "", config.agent_id)
        env_base_url = get_env_var("OLLAMA_BASE_URL", "", config.agent_id)

        # Set model from environment or config or default
        self.model = env_model or config.model or "llama2"

        # Update settings with environment values
        settings = config.settings or {}
        settings["base_url"] = (
            env_base_url or settings.get("base_url") or "http://localhost:11434"
        )

        # Rebuild the provider config with updated settings
        updated_config = ProviderConfig(
            name=config.name,
            model=config.model,
            settings=settings,
            agent_id=config.agent_id,
        )
        super().__init__(updated_config)

        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")

        # Check if Ollama server is running
        self._check_server()

    def _check_server(self) -> None:
        """Check if Ollama server is running."""
        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")
        try:
            response = requests.get(f"{self.settings.base_url}/api/version")
            response.raise_for_status()
            version = response.json().get("version")
            if not version:
                raise RuntimeError("Ollama server returned invalid version response")
        except RequestException as e:
            raise RuntimeError(
                f"Ollama server not running at {self.settings.base_url}: {str(e)}"
            ) from e

    async def chat(
        self,
        history: ChatHistory,
        kernel: Optional[Kernel] = None,
        functions: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """
        Process a chat message using Ollama.
        Ignores any function-calling logic (Ollama currently doesn't support it).
        """
        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")

        # Convert ChatHistory to Ollama's message list
        messages = []
        for msg in history.messages:
            if msg.role == AuthorRole.SYSTEM:
                messages.append({"role": "system", "content": msg.content})
            elif msg.role == AuthorRole.USER:
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == AuthorRole.ASSISTANT:
                messages.append({"role": "assistant", "content": msg.content})
            # We ignore function messages or treat them as assistant text if you prefer

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.settings.temperature,
                # Add other Ollama-specific parameters if needed
            },
        }

        # Send the request to Ollama
        url = f"{self.settings.base_url}/api/chat"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "error" in data:
                            raise RuntimeError(f"Ollama error: {data['error']}")
                        if "message" in data:
                            # Return the chunk as a normal assistant message
                            content = data["message"]["content"]
                            yield StreamingChatMessageContent(
                                role=AuthorRole.ASSISTANT,
                                content=content,
                                choice_index=0,
                            )
                    except json.JSONDecodeError:
                        # Could be partial JSON or empty line, skip
                        continue
