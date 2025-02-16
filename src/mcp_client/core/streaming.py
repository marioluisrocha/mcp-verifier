"""Streaming implementation for MCP client."""

import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from dataclasses import dataclass
from anthropic import AsyncAnthropic, AsyncStream

from .session import SessionManager

@dataclass
class StreamingMessage:
    """Represents a streaming chat message."""
    type: str  # 'content' or 'tool_call' or 'tool_result'
    content: str
    tool_info: Optional[Dict] = None

class StreamingManager:
    """Manages streaming for chat and tool interactions."""
    
    def __init__(self, session_manager: SessionManager, api_key: str):
        self.session_manager = session_manager
        self.client = AsyncAnthropic(api_key=api_key)
        
    async def stream_chat(self, messages: list, model: str = "claude-3-5-sonnet-20241022") -> AsyncGenerator[StreamingMessage, None]:
        """Stream a chat conversation with tool support.
        
        Args:
            messages: List of chat messages
            model: Model to use for chat
        
        Yields:
            StreamingMessage objects containing content or tool calls
        """
        # Get available tools
        tools = []
        for server_tools in self.session_manager.get_all_tools().values():
            tools.extend(server_tools)
            
        # Create chat completion
        stream = await self.client.messages.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True
        )
        
        async for chunk in stream:
            for content in chunk.content:
                if content.type == 'text':
                    yield StreamingMessage(
                        type='content',
                        content=content.text
                    )
                elif content.type == 'tool_use':
                    # Yield tool call
                    yield StreamingMessage(
                        type='tool_call',
                        content=f"Calling tool: {content.name}",
                        tool_info={
                            'name': content.name,
                            'args': content.input
                        }
                    )
                    
                    # Execute tool and yield result
                    try:
                        # Find server with this tool
                        server_name = None
                        for name, tools in self.session_manager.get_all_tools().items():
                            if any(t['name'] == content.name for t in tools):
                                server_name = name
                                break
                                
                        if server_name:
                            result = await self.session_manager.call_tool(
                                server_name,
                                content.name,
                                **content.input
                            )
                            
                            yield StreamingMessage(
                                type='tool_result',
                                content=result.content
                            )
                        else:
                            yield StreamingMessage(
                                type='tool_result',
                                content=f"Error: Tool {content.name} not found"
                            )
                            
                    except Exception as e:
                        yield StreamingMessage(
                            type='tool_result',
                            content=f"Error executing tool: {str(e)}"
                        )
