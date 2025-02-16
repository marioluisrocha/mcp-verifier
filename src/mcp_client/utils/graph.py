"""LangGraph-based agent implementation."""

from typing import List, Dict, Any, TypedDict, AsyncIterator

from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypeVar
from dataclasses import dataclass

from langgraph.graph import END, Graph
from langgraph.prebuilt import ToolExecutor
from langchain_core.messages import BaseMessage, AIMessage, FunctionMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_anthropic import ChatAnthropic
from langchain_core.utils.function_calling import convert_to_openai_function

NodeType = TypeVar("NodeType")

class AgentState(TypedDict):
    """State maintained by the agent during execution."""
    messages: List[BaseMessage]
    tools: List[Dict[str, Any]]
    next: str

@dataclass
class StreamEvent:
    """Event emitted during streaming."""
    type: str  # 'token', 'tool_start', 'tool_end', 'complete'
    data: Any

def create_agent_graph(api_key: str, tools: List[Dict[str, Any]]) -> CompiledStateGraph:
    """Create an agent execution graph.
    
    Args:
        api_key: Anthropic API key
        tools: List of available tools
        
    Returns:
        Configured execution graph
    """
    # Setup LLM
    load_dotenv()
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        streaming=True
    )
    
    # Convert tools to OpenAI format for function calling
    openai_tools = [convert_to_openai_function(tool) for tool in tools]
    
    # Setup prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful AI assistant with access to tools. "
                  "Use tools when appropriate to help users."),
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    # Tool executor
    tool_executor = ToolExecutor(tools)
    
    # Agent nodes
    
    async def agent(state: AgentState, config: Dict[str, Any]) -> AgentState:
        """Main agent node for generating responses."""
        # Format messages with prompt
        messages = prompt.format_messages(messages=state["messages"])
        
        # Get response with tool calls
        response = await llm.ainvoke(
            messages,
            tools=openai_tools,
            config={"stream_tokens": True}  # Enable token streaming
        )
        
        # Handle tool calls or final response
        if response.additional_kwargs.get("function_call"):
            state["next"] = "tools"
        else:
            state["messages"].append(AIMessage(content=response.content))
            state["next"] = END
            
        return state
        
    async def tools(state: AgentState, config: Dict[str, Any]) -> AgentState:
        """Tool execution node."""
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            state["next"] = END
            return state
            
        # Get tool call
        tool_call = last_message.additional_kwargs["function_call"]
        
        # Execute tool
        tool_result = await tool_executor.ainvoke({
            "name": tool_call["name"],
            "arguments": tool_call["arguments"]
        })
        
        # Add results to messages
        state["messages"].append(
            FunctionMessage(content=str(tool_result), name=tool_call["name"])
        )
        
        # Continue agent loop
        state["next"] = "agent"
        return state
        
    # Build graph
    workflow = Graph()
    
    workflow.add_node("agent", agent)
    workflow.add_node("tools", tools)
    
    # Add edges
    workflow.add_edge("agent", "tools")
    workflow.add_edge("tools", "agent")
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    return workflow.compile()

class StreamingAgentExecutor:
    """Executes agent graph with streaming support."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        
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
        # Create graph
        graph = create_agent_graph(self.api_key, tools)
        
        # Setup initial state
        state = AgentState(
            messages=messages,
            tools=tools,
            next="agent"
        )
        
        # Execute graph with streaming
        async for event in graph.astream(state, {"stream_tokens": True}):
            if isinstance(event, str):
                # Token event
                yield StreamEvent(type="token", data=event)
            elif isinstance(event, dict) and "function_call" in event:
                # Tool call event
                yield StreamEvent(type="tool_start", data=event["function_call"])
            elif isinstance(event, dict) and "function_result" in event:
                # Tool result event
                yield StreamEvent(type="tool_end", data=event["function_result"])
            elif event == END:
                # Completion event
                yield StreamEvent(type="complete", data=None)
