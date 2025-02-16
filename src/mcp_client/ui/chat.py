"""Streamlit-based chat interface with LangGraph integration."""

import streamlit as st
from typing import Optional
import asyncio
from dataclasses import dataclass, field
from langchain_core.messages import HumanMessage, AIMessage, FunctionMessage

from src.mcp_client.core.session import SessionManager
from src.mcp_client.utils.graph import StreamingAgentExecutor
from src.mcp_client.utils.mcp import ToolDefinition, MCPUtils

@dataclass
class ChatState:
    """Maintains chat interface state."""
    messages: list = field(default_factory=list)
    connected_servers: dict = field(default_factory=dict)
    current_tools: list = field(default_factory=list)

def initialize_state() -> ChatState:
    """Initialize or get chat state."""
    if 'chat_state' not in st.session_state:
        st.session_state.chat_state = ChatState()
    return st.session_state.chat_state

def display_message(msg: dict):
    """Display a chat message."""
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

def display_tool_call(name: str, args: dict):
    """Display a tool call."""
    with st.expander(f"🔧 Tool Call: {name}"):
        st.json(args)

async def handle_server_connection(state: ChatState,
                                 session_manager: SessionManager,
                                 server_name: str,
                                 script_path: str):
    """Handle connecting to a new server."""
    try:
        connection = await session_manager.connect_server(server_name, script_path)
        state.connected_servers[server_name] = connection
        
        # Update available tools
        for tool in connection.tools:
            tool_def = ToolDefinition(
                name=tool['name'],
                description=tool['description'],
                input_schema=tool['input_schema'],
                server_name=server_name
            )
            state.current_tools.append(MCPUtils.convert_tool_to_openai_function(tool_def))
            
        st.success(f"Connected to server: {server_name}")
        
        # Show available tools
        with st.expander(f"Available tools from {server_name}"):
            st.json(connection.tools)
            
    except Exception as e:
        st.error(f"Failed to connect to server {server_name}: {str(e)}")

async def process_message(state: ChatState,
                         session_manager: SessionManager,
                         agent_executor: StreamingAgentExecutor,
                         message: str):
    """Process a user message and stream the response."""
    
    # Create message placeholders
    response_placeholder = st.empty()
    tool_placeholder = st.empty()
    
    # Convert message to LangChain format
    lc_messages = []
    for msg in state.messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "function":
            lc_messages.append(FunctionMessage(
                content=msg["content"],
                name=msg["name"]
            ))
    
    # Add current message
    lc_messages.append(HumanMessage(content=message))
    
    # Add user message to state
    state.messages.append({"role": "user", "content": message})
    
    # Stream response
    current_text = ""
    async for event in agent_executor.astream(lc_messages, state.current_tools):
        if event.type == "token":
            current_text += event.data
            response_placeholder.markdown(current_text + "▌")
        
        elif event.type == "tool_start":
            with tool_placeholder:
                display_tool_call(
                    event.data["name"],
                    event.data["arguments"]
                )
                
            # Execute tool through MCP
            server_name = MCPUtils.find_server_for_tool(
                event.data["name"],
                {name: conn.tools for name, conn in state.connected_servers.items()}
            )
            
            if server_name:
                try:
                    result = await session_manager.call_tool(
                        server_name,
                        event.data["name"],
                        **event.data["arguments"]
                    )
                    current_text += f"\n\nTool Result:\n```\n{result.content}\n```\n"
                    response_placeholder.markdown(current_text + "▌")
                    
                except Exception as e:
                    error_msg = f"\n\nError executing tool: {str(e)}\n"
                    current_text += error_msg
                    response_placeholder.markdown(current_text + "▌")
        
        elif event.type == "complete":
            # Finalize response
            response_placeholder.markdown(current_text)
            # Add assistant response to state
            state.messages.append({"role": "assistant", "content": current_text})

def main():
    """Main chat interface."""
    st.title("MCP Chat Client")
    
    # Initialize state
    state = initialize_state()
    
    # Initialize managers
    session_manager = SessionManager()
    agent_executor = StreamingAgentExecutor(
        api_key=st.secrets["ANTHROPIC_API_KEY"]
    )
    
    # Server connection section
    with st.sidebar:
        st.header("Connect to Server")
        
        server_name = st.text_input("Server Name")
        script_path = st.text_input("Server Script Path")
        
        if st.button("Connect") and server_name and script_path:
            asyncio.run(handle_server_connection(
                state, session_manager, server_name, script_path
            ))
            
        # Show connected servers
        if state.connected_servers:
            st.header("Connected Servers")
            for name in state.connected_servers:
                st.text(f"• {name}")
                
        # Show available tools
        if state.current_tools:
            st.header("Available Tools")
            for tool in state.current_tools:
                with st.expander(tool["name"]):
                    st.write(f"**Description:** {tool['description']}")
                    st.write("**Parameters:**")
                    st.json(tool["parameters"])
                
    # Display chat history
    for message in state.messages:
        display_message(message)
        
    # Chat input
    if user_input := st.chat_input("Type your message here..."):
        asyncio.run(process_message(
            state,
            session_manager,
            agent_executor,
            user_input
        ))

if __name__ == "__main__":
    st.set_page_config(
        page_title="MCP Chat Client",
        page_icon="💬",
        layout="wide"
    )
    main()