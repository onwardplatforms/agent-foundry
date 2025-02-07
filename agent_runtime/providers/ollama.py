"""Ollama provider implementation."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
import requests
from pydantic import BaseModel, Field
from requests.exceptions import RequestException
from semantic_kernel.contents import (
    AuthorRole,
    ChatHistory,
    StreamingChatMessageContent,
)

from agent_runtime.env import get_env_var
from agent_runtime.providers.base import OllamaSettings, Provider, ProviderConfig


class OllamaProvider(Provider):
    """Ollama provider implementation."""

    def __init__(self, config: ProviderConfig) -> None:
        """Initialize provider."""
        # Get model and base URL from environment variables
        env_model = get_env_var(
            "OLLAMA_MODEL",
            "",
            config.agent_id,
        )
        env_base_url = get_env_var(
            "OLLAMA_BASE_URL",
            "",
            config.agent_id,
        )

        # Set model from environment or config or default
        self.model = env_model or config.model or "llama2"

        # Update settings with environment values
        settings = config.settings or {}
        settings["base_url"] = (
            env_base_url or settings.get("base_url") or "http://localhost:11434"
        )

        # Create a new config with updated settings
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
        self, history: ChatHistory
    ) -> AsyncIterator[StreamingChatMessageContent]:
        """Process a chat message using Ollama."""
        if not isinstance(self.settings, OllamaSettings):
            raise ValueError("Invalid settings type for Ollama provider")

        messages = []
        for msg in history.messages:
            if msg.role == AuthorRole.SYSTEM:
                messages.append({"role": "system", "content": msg.content})
            elif msg.role == AuthorRole.USER:
                messages.append({"role": "user", "content": msg.content})
            elif msg.role == AuthorRole.ASSISTANT:
                messages.append({"role": "assistant", "content": msg.content})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self.settings.temperature},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.settings.base_url}/api/chat",
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
                            yield StreamingChatMessageContent(
                                role=AuthorRole.ASSISTANT,
                                content=data["message"]["content"],
                                choice_index=0,
                            )
                    except json.JSONDecodeError:
                        continue
