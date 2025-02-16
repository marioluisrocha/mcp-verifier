"""Agent implementation for MCP client."""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain.agents import AgentExecutor
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain.agents.output_parsers import OpenAIFunctionsAgentOutputParser
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic

@dataclass
class AgentState:
    """Maintains agent state during conversation."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)

class MCPTool(BaseTool):
    """Wrapper for MCP tools to use with LangChain."""
    
    def __init__(self, name: str, description: str, schema: dict, executor):
        """Initialize MCP tool wrapper.
        
        Args:
            name: Tool name
            description: Tool description
            schema: JSON schema for tool input
            executor: Function to execute tool
        """
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
        self.executor = executor
        
    async def _arun(self, **kwargs):
        """Execute tool with given arguments."""
        return await self.executor(**kwargs)

class AgentManager:
    """Manages agent-based interactions."""
    
    def __init__(self, api_key: str):
        """Initialize agent manager.
        
        Args:
            api_key: Anthropic API key
        """

        load_dotenv()
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            streaming=True
        )
        
        # Setup base prompt
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful AI assistant with access to various tools. "
                      "Use these tools when appropriate to help users accomplish their tasks."),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
    def create_agent(self, tools: List[Dict], state: Optional[AgentState] = None) -> AgentExecutor:
        """Create an agent with given tools and state.
        
        Args:
            tools: List of tool definitions
            state: Optional agent state
        
        Returns:
            Configured AgentExecutor
        """
        # Convert MCP tools to LangChain tools
        langchain_tools = []
        for tool in tools:
            langchain_tools.append(MCPTool(
                name=tool['name'],
                description=tool['description'],
                schema=tool['input_schema'],
                executor=tool['executor']
            ))
            
        # Create agent
        agent = (
            {
                "input": lambda x: x["input"],
                "chat_history": lambda x: x["chat_history"],
                "agent_scratchpad": lambda x: format_to_openai_function_messages(
                    x["intermediate_steps"]
                ),
            }
            | self.prompt
            | self.llm
            | OpenAIFunctionsAgentOutputParser()
        )
        
        return AgentExecutor(
            agent=agent,
            tools=langchain_tools,
            verbose=True,
            return_intermediate_steps=True
        )
        
    async def run_agent(self, 
                       agent: AgentExecutor,
                       input_text: str,
                       state: AgentState) -> AgentState:
        """Run agent with input and update state.
        
        Args:
            agent: Configured AgentExecutor
            input_text: User input
            state: Current agent state
            
        Returns:
            Updated agent state
        """
        # Add user message to history
        state.messages.append({
            "role": "user",
            "content": input_text
        })
        
        # Run agent
        result = await agent.ainvoke({
            "input": input_text,
            "chat_history": state.messages
        })
        
        # Add assistant response to history
        state.messages.append({
            "role": "assistant",
            "content": result["output"]
        })
        
        return state
