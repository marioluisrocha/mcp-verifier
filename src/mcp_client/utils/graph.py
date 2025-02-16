"""Streaming agent implementation."""
from typing import AsyncIterator, Dict, Any, List
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

from src.mcp_client.core.agent import AgentManager

@dataclass
class StreamEvent:
    """Event emitted during streaming."""
    type: str
    data: Any

class StreamingAgentExecutor:
    """Executes agent with streaming support."""
    
    def __init__(self, api_key: str):
        """Initialize streaming executor."""
        self.agent_manager = AgentManager(api_key)
        
    async def astream(self,
                     messages: List[BaseMessage],
                     tools: List[Dict[str, Any]]) -> AsyncIterator[StreamEvent]:
        """Execute agent with streaming.
        
        Args:
            messages: Conversation history
            tools: Available tools
            
        Yields:
            Streaming events
        """
        # Create agent with tools
        agent = self.agent_manager.create_agent(tools)
        
        # Get input from last message
        input_text = messages[-1].content if messages else ""
        
        # Stream execution
        async for event in self.agent_manager.astream_chat(
            agent,
            input_text,
            messages[:-1]  # Chat history excludes current input
        ):
            yield event
