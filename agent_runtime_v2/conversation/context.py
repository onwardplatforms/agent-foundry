from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from semantic_kernel.contents import ChatHistory


@dataclass
class Message:
    """Represents a message in the conversation"""

    content: str
    role: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationContext:
    """Manages shared context and state for a conversation"""

    def __init__(self, conversation_id: str):
        self.id = conversation_id
        self.history = ChatHistory()
        self.shared_memory: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}

    async def add_message(self, message: Message) -> None:
        """Add a message to the conversation history"""
        if message.role == "user":
            self.history.add_user_message(message.content)
        elif message.role == "assistant":
            self.history.add_assistant_message(message.content)
        elif message.role == "system":
            self.history.add_system_message(message.content)

    def get_history(self) -> ChatHistory:
        """Get the conversation history"""
        return self.history

    async def store_memory(self, key: str, value: Any) -> None:
        """Store a value in shared memory"""
        self.shared_memory[key] = value

    def get_memory(self, key: str) -> Optional[Any]:
        """Retrieve a value from shared memory"""
        return self.shared_memory.get(key)
