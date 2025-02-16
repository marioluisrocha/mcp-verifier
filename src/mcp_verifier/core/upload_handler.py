"""Upload handling and processing for MCP server verification."""

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional
from zipfile import ZipFile, BadZipFile

from pydantic import BaseModel

from src.mcp_verifier.core.models import VerificationState

logger = logging.getLogger(__name__)

class UploadConfig(BaseModel):
    """Configuration for upload handling."""
    max_size_mb: int = 50
    allowed_extensions: set[str] = {'.py', '.js', '.ts', '.tsx', '.json', '.yaml', '.yml', '.toml', '.md'}
    temp_dir: str = "temp"
    extraction_timeout: int = 30  # seconds

class UploadHandler:
    """Handles server uploads and extraction."""
    
    def __init__(self, config: Optional[UploadConfig] = None):
        self.config = config or UploadConfig()
        self._ensure_temp_dir()
    
    def _ensure_temp_dir(self):
        """Ensure temporary directory exists."""
        Path(self.config.temp_dir).mkdir(parents=True, exist_ok=True)
    
    async def process_upload(self, server_zip_path: str, state: VerificationState) -> VerificationState:
        """
        Process an uploaded server ZIP file.
        
        Args:
            server_zip_path: Path to the uploaded ZIP file
            state: Current verification state
            
        Returns:
            Updated verification state
            
        Raises:
            ValueError: If upload is invalid
            BadZipFile: If ZIP file is corrupted
        """
        # Generate unique paths
        zip_path = Path(server_zip_path)
        extract_dir = Path(self.config.temp_dir) / str(uuid.uuid4())
        
        try:
            # Validate file size
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            if size_mb > self.config.max_size_mb:
                raise ValueError(f"ZIP file too large ({size_mb:.1f}MB > {self.config.max_size_mb}MB)")
            
            # Extract ZIP
            extract_dir.mkdir(parents=True)
            with ZipFile(zip_path) as zf:
                # Basic validation
                if self._has_dangerous_paths(zf.namelist()):
                    raise ValueError("ZIP contains dangerous paths")
                    
                # Extract files
                zf.extractall(extract_dir)
            
            # Update state
            state.server_path = str(extract_dir)
            state.current_stage = "extract_files"
            return state
            
        except BadZipFile:
            raise ValueError("Invalid or corrupted ZIP file")
            
        except Exception as e:
            # Cleanup on any error
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            raise
    
    def _has_dangerous_paths(self, paths: list[str]) -> bool:
        """Check for dangerous paths in ZIP."""
        for path in paths:
            norm_path = Path(path).resolve()
            if '..' in str(norm_path) or str(norm_path).startswith('/'):
                return True
        return False
        
    def cleanup(self, extract_dir: str):
        """Clean up extracted files."""
        try:
            shutil.rmtree(extract_dir)
        except Exception as e:
            logger.error(f"Failed to cleanup {extract_dir}: {e}")
