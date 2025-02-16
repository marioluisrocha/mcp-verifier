"""Main verification workflow for MCP servers."""

import logging
from pathlib import Path
from typing import Optional

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.mcp_verifier.core.models import VerificationState, VerificationResult
from src.mcp_verifier.core.upload_handler import UploadHandler, UploadConfig
from src.mcp_verifier.processors.file_processor import FileProcessor
from src.mcp_verifier.analyzers.security import SecurityAnalyzer
from src.mcp_verifier.analyzers.guidelines import GuidelinesAnalyzer
from src.mcp_verifier.analyzers.description import DescriptionAnalyzer
from src.mcp_verifier.utils.process import get_process_manager

logger = logging.getLogger(__name__)

class VerificationGraph:
    """Coordinates the MCP server verification process."""
    
    def __init__(self, upload_config: Optional[UploadConfig] = None):
        self.file_processor = FileProcessor()
        self.security_analyzer = SecurityAnalyzer()
        self.guidelines_analyzer = GuidelinesAnalyzer()
        self.description_analyzer = DescriptionAnalyzer()
        self.upload_handler = UploadHandler(upload_config)
        self.graph = self._build_graph()
        
    def _build_graph(self) -> CompiledStateGraph:
        """Build the verification workflow graph."""
        graph = StateGraph(VerificationState)
        
        # Add nodes for each verification stage
        graph.add_node("process_upload", self._process_upload)
        graph.add_node("extract_files", self._extract_files)
        graph.add_node("analyze_security", self._analyze_security)
        graph.add_node("analyze_guidelines", self._analyze_guidelines)
        graph.add_node("analyze_description", self._analyze_description)
        graph.add_node("verify_startup", self._verify_startup)
        graph.add_node("make_decision", self._make_decision)
        
        # Define the main workflow
        graph.add_edge(START, "process_upload")
        graph.add_edge("process_upload", "extract_files")
        graph.add_edge("extract_files", "analyze_security")
        graph.add_edge("analyze_security", "analyze_guidelines")
        graph.add_edge("analyze_guidelines", "analyze_description")
        graph.add_edge("analyze_description", "verify_startup")
        graph.add_edge("verify_startup", "make_decision")
        graph.add_edge("make_decision", END)
        
        # Add conditional edges for remediation
        graph.add_conditional_edges(
            "analyze_security",
            self._needs_security_fixes,
            {
                True: "analyze_security",  # Loop back for fixes
                False: "analyze_guidelines"
            }
        )
        
        return graph.compile()
        
    async def verify(self, 
                    uploaded_zip: str,
                    description: str,
                    config: Optional[dict] = None) -> VerificationResult:
        """
        Run the complete verification process on an MCP server.
        
        Args:
            uploaded_zip: Path to the uploaded ZIP file
            description: User-provided server description
            config: Optional configuration overrides
            
        Returns:
            VerificationResult with analysis results
        """
        logger.info(f"Starting verification for server from {uploaded_zip}")
        
        try:
            # Initialize state
            initial_state = VerificationState(
                files={},
                user_description=description,
                uploaded_zip=uploaded_zip,
                current_stage="init",
                security_issues=[],
                guideline_violations=[],
                description_match=0.0,
                status="pending"
            )
            
            # Run verification graph
            final_state = await self.graph.ainvoke(initial_state)
            
            # Create result
            result = VerificationResult(
                approved=final_state.status == "approved",
                security_issues=final_state.security_issues,
                guideline_violations=final_state.guideline_violations,
                description_match=final_state.description_match,
                extract_dir=final_state.extract_dir  # Include for cleanup
            )
            
            logger.info(f"Verification completed. Approved: {result.approved}")
            return result
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            raise
        finally:
            # Cleanup extracted files if they exist
            if initial_state.extract_dir:
                self.upload_handler.cleanup(initial_state.extract_dir)
                
    async def _process_upload(self, state: VerificationState) -> VerificationState:
        """Process uploaded ZIP file."""
        state.current_stage = "process_upload"
        return await self.upload_handler.process_upload(state.uploaded_zip, state)
        
    async def _extract_files(self, state: VerificationState) -> VerificationState:
        """Extract and process server files."""
        state.current_stage = "extract_files"
        state.files = await self.file_processor.extract_files(state.server_path)
        return state
        
    async def _analyze_security(self, state: VerificationState) -> VerificationState:
        """Run security analysis."""
        return await self.security_analyzer.analyze(state)
        
    async def _analyze_guidelines(self, state: VerificationState) -> VerificationState:
        """Check community guidelines compliance."""
        return await self.guidelines_analyzer.analyze(state)
        
    async def _analyze_description(self, state: VerificationState) -> VerificationState:
        """Compare implementation with description."""
        return await self.description_analyzer.analyze(state)
        
    async def _verify_startup(self, state: VerificationState) -> VerificationState:
        """Verify server startup and basic functionality."""
        state.current_stage = "verify_startup"
        
        try:
            # Determine server type and get appropriate manager
            server_type = self.file_processor.determine_server_type(state.files)
            process_manager = get_process_manager(server_type)
            
            # Find main file
            main_file = self.file_processor.get_main_file(state.files)
            if not main_file:
                raise ValueError("Could not determine main server file")
                
            # Create full path to main file
            full_path = Path(state.server_path) / main_file
                
            # Try to start server
            startup_success = await process_manager.start_server(str(full_path))
            if not startup_success:
                state.status = "rejected"
                return state
                
            # Verify it's healthy
            is_healthy = await process_manager.is_healthy()
            if not is_healthy:
                state.status = "rejected"
                return state
                
            return state
            
        except Exception as e:
            logger.error(f"Startup verification failed: {str(e)}")
            state.status = "rejected"
            return state
            
        finally:
            # Always try to cleanup
            if 'process_manager' in locals():
                await process_manager.stop_server()
                
    def _make_decision(self, state: VerificationState) -> VerificationState:
        """Make final verification decision."""
        # Check all criteria
        has_security_issues = len(state.security_issues) > 0
        has_critical_violations = any(
            'critical' in v.impact.lower() 
            for v in state.guideline_violations
        )
        poor_description_match = state.description_match < 0.8
        
        # Approve only if all checks pass
        if (has_security_issues or 
            has_critical_violations or 
            poor_description_match or 
            state.status == "rejected"):
            state.status = "rejected"
        else:
            state.status = "approved"
            
        return state
        
    def _needs_security_fixes(self, state: VerificationState) -> bool:
        """Check if security issues need to be fixed."""
        return len(state.security_issues) > 0 and any(
            'high' in issue.severity.lower() 
            for issue in state.security_issues
        )