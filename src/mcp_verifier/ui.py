"""Streamlit UI for MCP Server Verification."""
import logging
from pathlib import Path
import tempfile
import asyncio
import os

import streamlit as st
from dotenv import load_dotenv

from core.server_management import (
    MCPServerConfig,
    ServerStorageManager,
    ServerProcessManager,
    VerificationHandler
)
from core.models import VerificationResult
from src.mcp_client.utils.graph import StreamingAgentExecutor
from src.mcp_client.ui.chat import render_chat_interface


def save_uploaded_files(uploaded_files, temp_dir: Path) -> None:
    """Save uploaded files preserving directory structure."""
    for uploaded_file in uploaded_files:
        file_path = temp_dir / uploaded_file.name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("wb") as f:
            f.write(uploaded_file.getbuffer())


def display_verification_result(result: VerificationResult):
    """Display verification results in a formatted way."""
    if result.approved:
        st.success("✅ Verification Passed!")
    else:
        st.error("❌ Verification Failed!")

    if result.security_issues:
        st.subheader("Security Issues")
        for issue in result.security_issues:
            with st.expander(f"{issue.severity.upper()}: {issue.location}"):
                st.write(f"**Description:** {issue.description}")

    if result.guideline_violations:
        st.subheader("Guideline Violations")
        for violation in result.guideline_violations:
            with st.expander(f"{violation.rule}"):
                st.write(f"**Description:** {violation.description}")
                st.write(f"**Impact:** {violation.impact}")

    st.subheader("Description Match")
    st.progress(result.description_match)
    st.write(f"Match Score: {result.description_match:.1%}")


def initialize_state():
    """Initialize application state."""
    if 'server_managers' not in st.session_state:
        st.session_state.config_manager = MCPServerConfig(
            Path.home() / ".mcp" / "config.json"
        )
        st.session_state.storage_manager = ServerStorageManager(
            Path.home() / ".mcp" / "servers"
        )
        st.session_state.process_manager = ServerProcessManager(
            st.session_state.config_manager
        )
        st.session_state.verification_handler = VerificationHandler(
            st.session_state.config_manager,
            st.session_state.storage_manager,
            st.session_state.process_manager
        )


def render_server_management():
    """Render server management interface."""
    st.subheader("Managed Servers")

    # List current servers
    servers = st.session_state.config_manager.list_servers()
    for server in servers:
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            st.write(f"**{server['name']}**")
            st.write(f"Type: {server['type']}")

        with col2:
            status = "🟢 Running" if st.session_state.process_manager.is_running(server['name']) else "🔴 Stopped"
            st.write(status)

        with col3:
            if st.button("Restart", key=f"restart_{server['name']}"):
                with st.spinner(f"Restarting {server['name']}..."):
                    asyncio.run(st.session_state.process_manager.restart_server(server['name']))


def main():
    st.set_page_config(
        page_title="MCP Server Verification",
        page_icon="🔍",
        layout="wide"
    )

    # Load environment variables
    load_dotenv()

    # Initialize state
    initialize_state()

    # Initialize agent executor with running servers
    agent_executor = StreamingAgentExecutor(
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    # Create tabs for navigation
    tab1, tab2, tab3 = st.tabs(["Server Verification", "Server Management", "Chat"])

    with tab1:
        st.title("MCP Server Verification")

        with st.container():
            # Server name input
            server_name = st.text_input(
                "Server Name",
                placeholder="Enter a unique name for your server",
                help="This name will be used to identify your server"
            )

            description = st.text_area(
                "Server Description",
                placeholder="Describe your MCP server's functionality...",
                help="Provide a detailed description of what your server does"
            )

            uploaded_file = st.file_uploader(
                "Upload Server ZIP",
                type=['zip'],
                help="Upload your MCP server as a ZIP archive. The ZIP should contain all server files with preserved directory structure."
            )

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

            if all([uploaded_file, description, server_name]) and st.button("Verify Server"):
                with st.spinner("Verifying server..."):
                    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                        temp_zip.write(uploaded_file.getbuffer())
                        zip_path = Path(temp_zip.name)

                        try:
                            result = asyncio.run(
                                st.session_state.verification_handler.handle_verification(
                                    zip_path,
                                    description,
                                    server_name
                                )
                            )

                            if result:
                                display_verification_result(result)
                        finally:
                            try:
                                zip_path.unlink()
                            except:
                                pass

    with tab2:
        render_server_management()

    with tab3:
        render_chat_interface(agent_executor)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
