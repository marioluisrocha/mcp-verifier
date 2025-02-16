"""Agent implementation for MCP client."""
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain.agents.output_parsers import OpenAIFunctionsAgentOutputParser
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, AIMessage, FunctionMessage
from pydantic import BaseModel, Field

from src.mcp_client.core.session import SessionManager

@dataclass
class AgentState:
    """Maintains agent state during conversation."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StreamEvent:
    """Event emitted during streaming."""
    type: str  # 'token', 'tool_start', 'tool_end', 'complete'
    data: Any

class MCPTool(BaseTool):
    """Wrapper for MCP tools to use with LangChain."""
    
    def __init__(self, name: str, description: str, schema: dict, server_name: str, session_manager: SessionManager):
        """Initialize MCP tool wrapper."""
        self.server_name = server_name
        self.session_manager = session_manager
        
        super().__init__(
            name=name,
            description=description,
            args_schema=type(
                f"{name.title()}Schema",
                (BaseModel,),
                {k: (v.get('type', Any), Field(description=v.get('description', '')))
                 for k, v in schema.get('properties', {}).items()}
            )
        )
        
    async def _arun(self, **kwargs):
        """Execute tool with given arguments."""
        result = await self.session_manager.call_tool(
            self.server_name,
            self.name,
            **kwargs
        )
        return result.content

class AgentManager:
    """Manages agent-based interactions."""
    
    def __init__(self, api_key: str):
        """Initialize agent manager."""
        load_dotenv()
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            temperature=0,
            streaming=True
        )
        self.session_manager = SessionManager()
        
    async def add_server(self, server_name: str, script_path: str) -> List[Dict]:
        """Add MCP server and get its tools."""
        connection = await self.session_manager.connect_server(
            server_name, 
            script_path
        )
        return connection.tools
        
    def create_agent(self, tools: List[Dict]) -> AgentExecutor:
        """Create an agent with given tools."""
        # Convert MCP tools to LangChain tools
        langchain_tools = []
        for tool in tools:
            mcp_tool = MCPTool(
                name=tool['name'],
                description=tool['description'],
                schema=tool['input_schema'],
                server_name=tool['server_name'],
                session_manager=self.session_manager
            )
            langchain_tools.append(mcp_tool)
            
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful AI assistant with access to tools. "
                      "Use tools when appropriate to help users accomplish their tasks."),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # Create agent chain
        agent = (
            {
                "input": lambda x: x["input"],
                "chat_history": lambda x: x["chat_history"],
                "agent_scratchpad": lambda x: format_to_openai_function_messages(
                    x["intermediate_steps"]
                )
            }
            | prompt
            | self.llm
            | OpenAIFunctionsAgentOutputParser()
        )
        
        return AgentExecutor(
            agent=agent,
            tools=langchain_tools,
            verbose=True,
            return_intermediate_steps=True
        )
        
    async def astream_chat(self,
                        agent: AgentExecutor,
                        input_text: str,
                        chat_history: List[BaseMessage]) -> AsyncIterator[StreamEvent]:
        """Stream agent execution with tool calls."""
        
        async for chunk in agent.astream(
            {
                "input": input_text,
                "chat_history": chat_history
            }
        ):
            if isinstance(chunk, str):
                yield StreamEvent(type="token", data=chunk)
            elif isinstance(chunk, dict):
                if "function_call" in chunk:
                    yield StreamEvent(type="tool_start", data=chunk["function_call"])
                elif "function_result" in chunk:
                    yield StreamEvent(type="tool_end", data=chunk["function_result"])
            elif chunk == "complete":
                yield StreamEvent(type="complete", data=None)
