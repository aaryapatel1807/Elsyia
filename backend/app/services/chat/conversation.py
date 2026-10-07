"""
Conversation Management Service

Manages conversation history and context for chat sessions.
Phase 1: In-memory storage (no persistence).
Future: Vector database storage with RAG (Phase 2).
"""

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from app.core import get_logger
from app.models import Message, MessageRole, ConversationHistory

logger = get_logger("chat.conversation")


class ConversationManager:
    """
    Manages conversation history for multiple sessions.
    
    Phase 1: Simple in-memory storage.
    Phase 2: Will integrate with vector database for long-term memory.
    """
    
    def __init__(self):
        """Initialize conversation manager with empty storage."""
        self._conversations: Dict[UUID, ConversationHistory] = {}
        logger.info("Conversation manager initialized")
    
    def get_or_create(self, conversation_id: Optional[UUID] = None) -> ConversationHistory:
        """
        Get existing conversation or create new one.
        
        Args:
            conversation_id: Optional conversation ID. Creates new if None.
            
        Returns:
            Conversation history object
        """
        if conversation_id is None:
            conversation_id = uuid4()
            logger.info(f"Creating new conversation: {conversation_id}")
        
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = ConversationHistory(
                conversation_id=conversation_id,
                messages=[],
            )
            logger.debug(f"Initialized conversation storage: {conversation_id}")
        
        return self._conversations[conversation_id]
    
    def add_message(self, conversation_id: UUID, role: MessageRole, content: str) -> None:
        """
        Add message to conversation.
        
        Args:
            conversation_id: Conversation UUID
            role: Message role (user/assistant/system)
            content: Message content
        """
        conversation = self.get_or_create(conversation_id)
        message = Message(role=role, content=content)
        conversation.messages.append(message)
        conversation.updated_at = datetime.utcnow()
        
        logger.debug(
            f"Added {role.value} message to {conversation_id} "
            f"({len(conversation.messages)} total messages)"
        )
    
    def get_history(self, conversation_id: UUID) -> Optional[ConversationHistory]:
        """
        Get conversation history.
        
        Args:
            conversation_id: Conversation UUID
            
        Returns:
            Conversation history or None if not found
        """
        return self._conversations.get(conversation_id)
    
    def clear(self, conversation_id: UUID) -> None:
        """
        Clear conversation history.
        
        Args:
            conversation_id: Conversation UUID to clear
        """
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            logger.info(f"Cleared conversation: {conversation_id}")
        else:
            logger.warning(f"Attempted to clear non-existent conversation: {conversation_id}")
    
    def format_for_llm(self, conversation_id: UUID, system_prompt: str) -> str:
        """
        Format conversation for LLM consumption.
        
        Converts conversation history into a prompt string that includes
        system instructions and all previous messages.
        
        Args:
            conversation_id: Conversation UUID
            system_prompt: System prompt defining AI behavior
            
        Returns:
            Formatted prompt string
        """
        conversation = self.get_or_create(conversation_id)
        
        # Start with system prompt
        formatted = f"System: {system_prompt}\n\n"
        
        # Add conversation history
        for msg in conversation.messages:
            role_name = msg.role.value.capitalize()
            formatted += f"{role_name}: {msg.content}\n"
        
        logger.debug(
            f"Formatted conversation {conversation_id} with "
            f"{len(conversation.messages)} messages"
        )
        
        return formatted
    
    def get_message_count(self, conversation_id: UUID) -> int:
        """
        Get number of messages in conversation.
        
        Args:
            conversation_id: Conversation UUID
            
        Returns:
            Message count
        """
        conversation = self._conversations.get(conversation_id)
        return len(conversation.messages) if conversation else 0
    
    def get_all_conversation_ids(self) -> list[UUID]:
        """
        Get all active conversation IDs.
        
        Returns:
            List of conversation UUIDs
        """
        return list(self._conversations.keys())

    def compact(self, conversation_id: UUID, summary_text: str, keep_last_n: int) -> int:
        """Fold old messages into the rolling summary, keeping the newest N.

        Returns the number of messages dropped. The summary is appended to
        any existing summary and capped so it can't grow unbounded.
        """
        conversation = self._conversations.get(conversation_id)
        if conversation is None or len(conversation.messages) <= keep_last_n:
            return 0
        dropped = len(conversation.messages) - keep_last_n
        conversation.messages = conversation.messages[-keep_last_n:]
        existing = (conversation.summary + "\n") if conversation.summary else ""
        conversation.summary = (existing + summary_text.strip()).strip()[-4000:]
        conversation.updated_at = datetime.utcnow()
        logger.debug(
            "Compacted conversation %s: dropped %d messages", conversation_id, dropped
        )
        return dropped


# Global singleton instance
conversation_manager = ConversationManager()
