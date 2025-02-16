"""Streamlit-based chat interface for MCP client."""

import streamlit as st
from typing import Optional
import asyncio
from dataclasses import dataclass, field

from ..core.session import SessionManager
from ..core.streaming import StreamingManager
from ..core.agent import AgentManager, AgentState

@dataclass
class ChatState:
    """Maintains chat interface state."""
    messages: list = field(default_factory=list)
    connected_servers: dict = field(default_factory=dict)
    agent_state: Optional[AgentState] = None

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
        st.success(f"Connected to server: {server_name}")
        
        # Show available tools
        with st.expander(f"Available tools from {server_name}"):
            st.json(connection.tools)
            
    except Exception as e:
        st.error(f"Failed to connect to server {server_name}: {str(e)}")

async def process_message(state: ChatState,
                         streaming_manager: StreamingManager,
                         agent_manager: AgentManager,
                         message: str):
    """Process a user message and stream the response."""
    
    # Create placeholder for streaming response
    response_placeholder = st.empty()
    tool_placeholder = st.empty()
    current_response = []
    
    # Initialize agent if needed
    if not state.agent_state:
        state.agent_state = AgentState()
    
    # Get all available tools
    tools = []
    for server_tools in state.connected_servers.values():
        tools.extend(server_tools.tools)
    
    # Create agent
    agent = agent_manager.create_agent(tools, state.agent_state)
    
    # Add user message to state
    state.messages.append({"role": "user", "content": message})
    
    # Stream response
    current_text = ""
    async for chunk in streaming_manager.stream_chat([{"role": "user", "content": message}]):
        if chunk.type == 'content':
            current_text += chunk.content
            response_placeholder.markdown(current_text + "▌")
        elif chunk.type == 'tool_call':
            with tool_placeholder:
                display_tool_call(
                    chunk.tool_info['name'],
                    chunk.tool_info['args']
                )
        elif chunk.type == 'tool_result':
            current_text += f"\n\nTool Result:\n```\n{chunk.content}\n```\n"
            response_placeholder.markdown(current_text + "▌")
    
    # Finalize response
    response_placeholder.markdown(current_text)
    
    # Add assistant response to state
    state.messages.append({"role": "assistant", "content": current_text})
    
    # Update agent state
    state.agent_state = await agent_manager.run_agent(
        agent,
        message,
        state.agent_state
    )

def main():
    """Main chat interface."""
    st.title("MCP Chat Client")
    
    # Initialize state
    state = initialize_state()
    
    # Initialize managers
    session_manager = SessionManager()
    streaming_manager = StreamingManager(
        session_manager=session_manager,
        api_key=st.secrets["ANTHROPIC_API_KEY"]
    )
    agent_manager = AgentManager(api_key=st.secrets["ANTHROPIC_API_KEY"])
    
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
                
    # Display chat history
    for message in state.messages:
        display_message(message)
        
    # Chat input
    if user_input := st.chat_input("Type your message here..."):
        asyncio.run(process_message(
            state,
            streaming_manager,
            agent_manager,
            user_input
        ))

if __name__ == "__main__":
    st.set_page_config(
        page_title="MCP Chat Client",
        page_icon="💬",
        layout="wide"
    )
    main()