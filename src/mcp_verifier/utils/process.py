"""Process management utilities for server verification."""

import asyncio
import logging
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import psutil
import functools

from src.mcp_verifier.core.interfaces import ProcessManager
from src.mcp_verifier.utils.dependency_installer import DependencyInstaller

logger = logging.getLogger(__name__)

class PackageBuilder:
    """Handles building packages for different types of servers."""
    
    @staticmethod
    async def build_python_package(server_path: str) -> Optional[str]:
        """Build Python package and return path to wheel/sdist."""
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                # First ensure build package is installed
                install_result = await loop.run_in_executor(
                    pool,
                    functools.partial(
                        subprocess.run,
                        ['pip', 'install', 'build'],
                        capture_output=True,
                        text=True
                    )
                )
                
                if install_result.returncode != 0:
                    logger.error(f"Failed to install build package: {install_result.stderr}")
                    return None

                # Run build command in the package directory
                process = await loop.run_in_executor(
                    pool,
                    functools.partial(
                        subprocess.run,
                        ['python', '-m', 'build', '.'],
                        capture_output=True,
                        text=True,
                        cwd=server_path
                    )
                )

                if process.returncode != 0:
                    logger.error(f"Failed to build Python package: {process.stderr}")
                    return None

                # Find the built wheel in dist directory
                dist_path = Path(server_path) / 'dist'
                wheels = list(dist_path.glob('*.whl'))
                if wheels:
                    return str(wheels[0])
                
                # Fallback to sdist if no wheel
                sdists = list(dist_path.glob('*.tar.gz'))
                if sdists:
                    return str(sdists[0])
                
                return None
                
        except Exception as e:
            logger.error(f"Error building Python package: {str(e)}")
            return None

    @staticmethod
    async def build_node_package(server_path: str) -> Tuple[Optional[str], str]:
        """Build Node.js package and return path to tarball and package manager type."""
        try:
            # Detect package manager
            pkg_manager = PackageBuilder.detect_node_package_manager(server_path)
            
            # Prepare command based on package manager
            if pkg_manager == "pnpm":
                cmd = ["pnpm", "pack"]
            elif pkg_manager == "yarn":
                cmd = ["yarn", "pack"]
            else:  # npm
                cmd = ["npm", "pack"]

            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                # Run in thread pool to avoid blocking
                process = await loop.run_in_executor(
                    pool,
                    functools.partial(
                        subprocess.run,
                        cmd,
                        capture_output=True,
                        text=True,
                        cwd=server_path
                    )
                )
            
            if process.returncode != 0:
                logger.error(f"Failed to build Node package: {process.stderr}")
                return None, pkg_manager
                
            # Find the created tarball
            tarball = process.stdout.strip()
            if tarball:
                return str(Path(server_path) / tarball), pkg_manager
                
            return None, pkg_manager
            
        except Exception as e:
            logger.error(f"Error building Node package: {str(e)}")
            return None, "npm"  # Default to npm on error
            
    @staticmethod
    def detect_node_package_manager(directory: str) -> str:
        """Detect which package manager is used in the project."""
        path = Path(directory)
        if (path / "pnpm-lock.yaml").exists():
            return "pnpm"
        elif (path / "yarn.lock").exists():
            return "yarn"
        elif (path / "package-lock.json").exists():
            return "npm"
        return "npm"  # Default to npm if no lock file found

class BaseMCPProcessManager(ProcessManager):
    """Base class for MCP server process managers."""
    
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.startup_timeout = 30  # seconds
        self.dependency_installer = DependencyInstaller()

    async def install_dependencies(self, server_path: str, server_type: str) -> bool:
        """Install server dependencies."""
        return await self.dependency_installer.install_dependencies(server_path, server_type)
        
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
            
        return self.process.returncode == 0
        
    async def _wait_for_healthy(self) -> bool:
        """Wait for server to become healthy."""
        MAX_ATTEMPTS = 10
        DELAY = 0.5
        
        for _ in range(MAX_ATTEMPTS):
            if await self.is_healthy():
                return True
            await asyncio.sleep(DELAY)
            
        return False

class PythonProcessManager(BaseMCPProcessManager):
    """Process manager for Python MCP servers."""
    
    async def start_server(self, package_path: str, package_name: str) -> bool:
        """
        Start a Python MCP server process using pipx.
        
        Args:
            package_path: Path to the built package (wheel or sdist)
            
        Returns:
            True if server started successfully
        """
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                # Ensure pipx is installed
                install_result = await loop.run_in_executor(
                    pool,
                    functools.partial(
                        subprocess.run,
                        ['pip', 'install', 'pipx'],
                        capture_output=True,
                        text=True
                    )
                )
                
                if install_result.returncode != 0:
                    logger.error(f"Failed to install pipx: {install_result.stderr}")
                    return False
                
                # Start with pipx
                process = await loop.run_in_executor(
                    pool,
                    functools.partial(
                        subprocess.run,
                        ['pipx', 'run', '--spec', package_path, package_name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL
                    )
                )
            
            # Set process for health checks
            self.process = process
            
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

class NodeProcessManager(BaseMCPProcessManager):
    """Process manager for Node.js MCP servers."""
    
    async def start_server(self, package_info: Tuple[str, str]) -> bool:
        """
        Start a Node.js MCP server process using appropriate package manager.
        
        Args:
            package_info: Tuple of (package_path, package_manager)
            
        Returns:
            True if server started successfully
        """
        package_path, pkg_manager = package_info
        
        try:
            # Prepare command based on package manager
            if pkg_manager == "pnpm":
                cmd = ["pnpm", "dlx", package_path]
            elif pkg_manager == "yarn":
                cmd = ["yarn", "dlx", package_path]
            else:  # npm
                cmd = ["npx", "--yes", package_path]
            
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                # Start server using appropriate package manager
                process = await loop.run_in_executor(
                    pool,
                    functools.partial(
                        subprocess.run,
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL
                    )
                )
            
            # Set process for health checks
            self.process = process
            
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