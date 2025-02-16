"""Streamlit UI for MCP Server Verification."""

import streamlit as st
import tempfile
from pathlib import Path
import asyncio
from typing import Optional

from core.verification import VerificationGraph
from core.models import VerificationResult

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

async def verify_server(temp_dir: Path, description: str) -> Optional[VerificationResult]:
    """Run verification process."""
    try:
        verifier = VerificationGraph()
        result = await verifier.verify(str(temp_dir), description)
        return result
    except Exception as e:
        st.error(f"Verification failed: {str(e)}")
        return None

def main():
    st.title("MCP Server Verification")
    
    # Description input
    description = st.text_area(
        "Server Description",
        placeholder="Describe your MCP server's functionality...",
        help="Provide a detailed description of what your server does"
    )
    
    # File uploader
    uploaded_files = st.file_uploader(
        "Upload Server Files",
        accept_multiple_files=True,
        type=['py', 'js', 'ts', 'tsx', 'json', 'yaml', 'yml'],
        help="Upload all files that comprise your MCP server"
    )
    
    if uploaded_files and description and st.button("Verify Server"):
        with st.spinner("Verifying server..."):
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Save uploaded files
                save_uploaded_files(uploaded_files, temp_path)
                
                # Progress indicator
                progress_text = "Running verification..."
                progress_bar = st.progress(0)
                
                # Run verification
                result = asyncio.run(verify_server(temp_path, description))
                
                if result:
                    display_verification_result(result)
                    
                # Cleanup happens automatically when context exits

if __name__ == "__main__":
    st.set_page_config(
        page_title="MCP Server Verification",
        page_icon="🔍",
        layout="wide"
    )
    main()