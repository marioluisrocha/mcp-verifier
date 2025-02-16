"""Streamlit UI for MCP Server Verification."""

import streamlit as st
import tempfile
from pathlib import Path
import asyncio
from typing import Optional
from dataclasses import dataclass, field
from langchain_core.messages import HumanMessage, AIMessage, FunctionMessage
import os

from core.verification import VerificationGraph
from core.models import VerificationResult
from core.upload_handler import UploadConfig
from src.mcp_client.core.session import SessionManager
from src.mcp_client.utils.graph import StreamingAgentExecutor
from src.mcp_client.utils.mcp import ToolDefinition, MCPUtils

def save_uploaded_files(uploaded_files, temp_dir: Path) -> None:
    """Save uploaded files preserving directory structure."""
    for uploaded_file in uploaded_files:
        # Get relative path from file name
        file_path = temp_dir / uploaded_file.name

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Save file
        with file_path.open("wb") as f:
            f.write(uploaded_file.getbuffer())

def display_verification_result(result: VerificationResult):
    """Display verification results in a formatted way."""
    if result.approved:
        st.success("✅ Verification Passed!")
    else:
        st.error("❌ Verification Failed!")
        
    # Security Issues
    if result.security_issues:
        st.subheader("Security Issues")
        for issue in result.security_issues:
            with st.expander(f"{issue.severity.upper()}: {issue.location}"):
                st.write(f"**Description:** {issue.description}")
                st.write(f"**Recommendation:** {issue.recommendation}")
                
    # Guideline Violations
    if result.guideline_violations:
        st.subheader("Guideline Violations")
        for violation in result.guideline_violations:
            with st.expander(f"{violation.rule}"):
                st.write(f"**Description:** {violation.description}")
                st.write(f"**Impact:** {violation.impact}")
                
    # Description Match
    st.subheader("Description Match")
    st.progress(result.description_match)
    st.write(f"Match Score: {result.description_match:.1%}")

async def verify_server(zip_path: Path, description: str) -> Optional[VerificationResult]:
    """Run verification process."""
    try:
        verifier = VerificationGraph(UploadConfig())
        result = await verifier.verify(str(zip_path), description)
        return result
    except Exception as e:
        st.error(f"Verification failed: {str(e)}")
        return None

@dataclass
class ChatState:
    """Maintains chat interface state."""
    messages: list = field(default_factory=list)
    connected_servers: dict = field(default_factory=dict)
    current_tools: list = field(default_factory=list)

def initialize_chat_state() -> ChatState:
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

def render_chat_interface():
    """Render the chat interface in the main area."""
    st.title("MCP Chat")

    # Initialize state and managers
    state = initialize_chat_state()
    session_manager = SessionManager()
    agent_executor = StreamingAgentExecutor(
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    # Display chat history
    st.header("Chat History")
    for message in state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if user_input := st.chat_input("Type your message here..."):
        asyncio.run(process_message(
            state,
            session_manager,
            agent_executor,
            user_input
        ))

def main():
    st.set_page_config(
        page_title="MCP Server Verification",
        page_icon="🔍",
        layout="wide"
    )

    # Create tabs for navigation
    tab1, tab2 = st.tabs(["Server Verification", "Chat"])

    with tab1:
        st.title("MCP Server Verification")

        with st.container():
            # Server description
            description = st.text_area(
                "Server Description",
                placeholder="Describe your MCP server's functionality...",
                help="Provide a detailed description of what your server does"
            )

            # ZIP file uploader
            uploaded_file = st.file_uploader(
                "Upload Server ZIP",
                type=['zip'],
                help="Upload your MCP server as a ZIP archive. The ZIP should contain all server files with preserved directory structure."
            )

            # Guidelines for ZIP creation
            with st.expander("ZIP File Guidelines"):
                st.markdown("""
                ### How to prepare your server ZIP:
                1. Ensure all server files are in their correct directory structure
                2. Include all necessary files (.py, .js, .ts, .json, etc.)
                3. Do not include:
                   - Virtual environments (venv, node_modules)
                   - Compiled files (__pycache__, .pyc)
                   - System or hidden files (.DS_Store, Thumbs.db)
                4. Maximum size: 50MB
                """)

            if uploaded_file and description and st.button("Verify Server"):
                with st.spinner("Verifying server..."):
                    # Save uploaded ZIP
                    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                        temp_zip.write(uploaded_file.getbuffer())
                        zip_path = Path(temp_zip.name)

                        try:
                            # Progress indicator
                            progress_text = "Running verification..."
                            progress_bar = st.progress(0)

                            # Run verification
                            result = asyncio.run(verify_server(zip_path, description))

                            if result:
                                display_verification_result(result)
                        finally:
                            # Cleanup temporary zip file
                            try:
                                zip_path.unlink()
                            except:
                                pass
    with tab2:
        render_chat_interface()

if __name__ == "__main__":
    main()