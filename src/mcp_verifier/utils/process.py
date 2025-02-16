"""Process management utilities for server verification."""

import asyncio
import logging
import signal
from typing import Optional, Dict, Any
import psutil

from src.mcp_verifier.core.interfaces import ProcessManager

logger = logging.getLogger(__name__)

class PythonProcessManager(ProcessManager):
    """Process manager for Python MCP servers."""
    
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.startup_timeout = 30  # seconds
        
    async def start_server(self, main_file: str) -> bool:
        """
        Start a Python MCP server process.
        
        Args:
            main_file: Path to server's main Python file
            
        Returns:
            True if server started successfully
        """
        try:
            # Create subprocess
            import subprocess
            self.process = subprocess.Popen(
                ['python', main_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL
            )
            # self.process = await asyncio.create_subprocess_exec(
            #     'python',
            #     main_file,
            #     stdout=asyncio.subprocess.PIPE,
            #     stderr=asyncio.subprocess.PIPE,
            #     # Don't pass through stdin to avoid hanging
            #     stdin=asyncio.subprocess.DEVNULL
            # )
            
            # Wait for startup with timeout
            try:
                return await asyncio.wait_for(
                    self._wait_for_healthy(),
                    timeout=self.startup_timeout
                )
            except asyncio.TimeoutError:
                logger.error("Server startup timed out")
                await self.stop_server()
                return False
                
        except Exception as e:
            logger.error(f"Failed to start server: {str(e)}")
            return False
            
    async def stop_server(self) -> None:
        """Stop the server process and cleanup."""
        if self.process is None:
            return
            
        try:
            # Try graceful shutdown first
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                return
            except asyncio.TimeoutError:
                pass
                
            # Force kill if necessary    
            self.process.kill()
            await self.process.wait()
            
        except Exception as e:
            logger.error(f"Error stopping server: {str(e)}")
        finally:
            self.process = None
            
    async def is_healthy(self) -> bool:
        """Check if server process is running and responsive."""
        if self.process is None:
            return False
            
        # Check if process is still running
        if self.process.returncode is not None:
            return False
            
        # todo Could add additional health checks here, like:
        # - Memory usage
        # - CPU usage
        # - Network connectivity
        # - Response to ping
        
        return True
        
    async def _wait_for_healthy(self) -> bool:
        """Wait for server to become healthy."""
        MAX_ATTEMPTS = 10
        DELAY = 0.5
        
        for _ in range(MAX_ATTEMPTS):
            if await self.is_healthy():
                return True
            await asyncio.sleep(DELAY)
            
        return False


class NodeProcessManager(ProcessManager):
    """Process manager for Node.js MCP servers."""
    
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.startup_timeout = 30  # seconds
        
    async def start_server(self, main_file: str) -> bool:
        """
        Start a Node.js MCP server process.
        
        Args:
            main_file: Path to server's main JS/TS file
            
        Returns:
            True if server started successfully
        """
        try:
            # Use node or ts-node based on file extension
            command = 'node' if main_file.endswith('.js') else 'ts-node'
            
            self.process = await asyncio.create_subprocess_exec(
                command,
                main_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL
            )
            
            try:
                return await asyncio.wait_for(
                    self._wait_for_healthy(),
                    timeout=self.startup_timeout
                )
            except asyncio.TimeoutError:
                logger.error("Server startup timed out")
                await self.stop_server()
                return False
                
        except Exception as e:
            logger.error(f"Failed to start server: {str(e)}")
            return False
            
    async def stop_server(self) -> None:
        """Stop the server process and cleanup."""
        if self.process is None:
            return
            
        try:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                return
            except asyncio.TimeoutError:
                pass
                
            self.process.kill()
            await self.process.wait()
            
        except Exception as e:
            logger.error(f"Error stopping server: {str(e)}")
        finally:
            self.process = None
            
    async def is_healthy(self) -> bool:
        """Check if server process is running and responsive."""
        if self.process is None:
            return False
            
        return self.process.returncode is None
        
    async def _wait_for_healthy(self) -> bool:
        """Wait for server to become healthy."""
        MAX_ATTEMPTS = 10
        DELAY = 0.5
        
        for _ in range(MAX_ATTEMPTS):
            if await self.is_healthy():
                return True
            await asyncio.sleep(DELAY)
            
        return False


def get_process_manager(server_type: str) -> ProcessManager:
    """
    Factory function to get appropriate process manager.
    
    Args:
        server_type: Either 'python' or 'node'
        
    Returns:
        ProcessManager instance
        
    Raises:
        ValueError: If server_type is invalid
    """
    if server_type == 'python':
        return PythonProcessManager()
    elif server_type == 'node':
        return NodeProcessManager()
    else:
        raise ValueError(f"Invalid server type: {server_type}")