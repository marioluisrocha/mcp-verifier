"""File processing utilities for MCP server verification."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..core.models import ServerFile

logger = logging.getLogger(__name__)

class FileProcessor:
    """Handles extraction and analysis of MCP server files."""
    
    # Supported file types
    VALID_EXTENSIONS: Set[str] = {'.py', '.js', '.ts', '.tsx', '.json', '.yaml', '.yml'}
    
    async def extract_files(self, path: str) -> Dict[str, ServerFile]:
        """
        Extract and categorize all relevant files from the server directory.
        
        Args:
            path: Path to the server root directory
            
        Returns:
            Dictionary mapping file paths to ServerFile objects
            
        Raises:
            FileNotFoundError: If path doesn't exist
            ValueError: If no valid server files found
        """
        server_path = Path(path)
        if not server_path.exists():
            raise FileNotFoundError(f"Server path not found: {path}")
            
        files: Dict[str, ServerFile] = {}
        
        # Find all relevant files
        for file_path in server_path.rglob("*"):
            if not file_path.is_file():
                continue
                
            if file_path.suffix not in self.VALID_EXTENSIONS:
                continue
                
            try:
                # Read file content using JetBrains API
                rel_path = str(file_path.relative_to(server_path))
                content = await self._read_file(str(file_path))
                
                files[rel_path] = ServerFile(
                    path=rel_path,
                    content=content,
                    file_type=file_path.suffix[1:]  # Remove the dot
                )
                
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {str(e)}")
                continue
        
        if not files:
            raise ValueError(f"No valid server files found in {path}")
            
        return files
    
    async def _read_file(self, path: str) -> str:
        """
        Read file content using JetBrains API.
        
        Args:
            path: Path to the file to read
            
        Returns:
            File content as string
            
        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file cannot be read
        """
        try:
            content = await self._try_read_file(path)
            if content is None:
                raise FileNotFoundError(f"File not found: {path}")
            return content
        except Exception as e:
            raise IOError(f"Failed to read file {path}: {str(e)}")
            
    async def _try_read_file(self, path: str) -> Optional[str]:
        """Attempt to read file content with proper encoding."""
        try:
            result = await get_file_text_by_path(path)
            if isinstance(result, str) and not result.startswith("error"):
                return result
            return None
        except Exception:
            return None
            
    def get_main_file(self, files: Dict[str, ServerFile]) -> Optional[str]:
        """
        Find the likely main file of the MCP server.
        
        Args:
            files: Dictionary of files in the server
            
        Returns:
            Path to main file or None if not found
        """
        # Common main file patterns
        main_patterns = [
            'server.py', 'server.js', 'server.ts',
            'index.py', 'index.js', 'index.ts',
            'main.py', 'main.js', 'main.ts',
            'app.py', 'app.js', 'app.ts'
        ]
        
        # First check root directory
        for pattern in main_patterns:
            if pattern in files:
                return pattern
                
        # Then check subdirectories
        for pattern in main_patterns:
            for path in files:
                if path.endswith(pattern):
                    return path
                    
        return None
        
    def determine_server_type(self, files: Dict[str, ServerFile]) -> str:
        """
        Determine if this is a Python or Node.js server.
        
        Args:
            files: Dictionary of files in the server
            
        Returns:
            'python' or 'node'
            
        Raises:
            ValueError: If server type cannot be determined
        """
        python_files = [f for f in files.values() if f.file_type == 'py']
        node_files = [f for f in files.values() if f.file_type in ('js', 'ts', 'tsx')]
        
        if python_files and not node_files:
            return 'python'
        elif node_files and not python_files:
            return 'node'
        
        # If both types exist, check package files
        has_requirements = any('requirements.txt' in f for f in files)
        has_poetry = any('pyproject.toml' in f for f in files)
        has_package_json = any('package.json' in f for f in files)
        
        if (has_requirements or has_poetry) and not has_package_json:
            return 'python'
        elif has_package_json and not (has_requirements or has_poetry):
            return 'node'
            
        raise ValueError("Cannot determine server type - mixed Python and Node.js files found")