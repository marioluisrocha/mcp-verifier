"""Chat interface implementation."""
import asyncio
import threading
from typing import AsyncGenerator, Callable

import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from src.mcp_client.core.agent import AgentManager
from src.mcp_client.utils.graph import StreamingAgentExecutor


def to_sync_generator(async_gen: AsyncGenerator):
    """Convert async generator to sync generator."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    while True:
        try:
            yield loop.run_until_complete(anext(async_gen))
        except StopAsyncIteration:
            break


def run_in_background(func: Callable, *args, **kwargs) -> threading.Thread:
    """Run function in background thread."""
    thread = threading.Thread(target=func, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()
    return thread


async def yield_agent_results(agent_executor: StreamingAgentExecutor, 
                            messages: list,
                            tools: list,
                            input_text: str):
    """Yield streaming results from agent execution."""
    # Convert messages to LangChain format
    lc_messages = []
    for msg in messages:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))
    
    # Add current message
    lc_messages.append(HumanMessage(content=input_text))
    
    # Stream response
    current_response = ""
    async for event in agent_executor.astream(lc_messages, tools):
        if event.type == "token":
            current_response += event.data
            yield current_response
        elif event.type == "tool_start":
            tool_info = f"\n\n🔧 Using tool: {event.data['name']}\n"
            current_response += tool_info
            yield current_response
        elif event.type == "tool_end":
            result_info = f"\nTool result: {event.data}\n\n"
            current_response += result_info
            yield current_response


def initialize_chat_state():
    """Initialize or get chat state."""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'tools' not in st.session_state:
        st.session_state.tools = []


def render_chat_interface(agent_executor: StreamingAgentExecutor):
    """Render the chat interface."""
    st.title("MCP Chat")
    
    # Initialize state
    initialize_chat_state()
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    if chat_input := st.chat_input("Type your message here..."):
        # Display user message
        with st.chat_message("user"):
            st.write(chat_input)
        
        # Add to message history
        st.session_state.messages.append({
            "role": "user",
            "content": chat_input
        })
        
        # Display assistant response with streaming
        with st.chat_message("assistant"):
            response = st.write_stream(
                to_sync_generator(
                    yield_agent_results(
                        agent_executor,
                        st.session_state.messages,
                        st.session_state.tools,
                        chat_input
                    )
                )
            )
            
            # Add assistant response to history
            st.session_state.messages.append({
                "role": "assistant",
                "content": response
            })
