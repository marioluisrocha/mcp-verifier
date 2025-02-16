"""Anthropic API client utilities."""

from typing import Optional, AsyncGenerator
from anthropic import AsyncAnthropic
from anthropic.types import MessageStreamEvent

class AnthropicClient:
    """Wrapper for Anthropic API client."""
    
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)
        
    async def stream_chat(self,
                         messages: list,
                         tools: Optional[list] = None,
                         model: str = "claude-3-5-sonnet-20241022") -> AsyncGenerator[MessageStreamEvent, None]:
        """Stream a chat conversation.
        
        Args:
            messages: List of chat messages
            tools: Optional list of tools
            model: Model to use
            
        Yields:
            Message stream events
        """
        stream = await self.client.messages.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True
        )
        
        async for chunk in stream:
            yield chunk