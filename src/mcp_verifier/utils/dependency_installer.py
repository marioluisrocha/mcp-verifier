"""Dependency installation utilities for MCP server verification."""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class DependencyInstaller:
    """Handles installation of Python and Node.js dependencies."""

    def __init__(self):
        self.install_timeout = 300  # 5 minutes

    async def install_dependencies(self, server_path: str, server_type: str) -> bool:
        """
        Install dependencies for a server.

        Args:
            server_path: Path to the server directory
            server_type: 'python' or 'node'

        Returns:
            True if installation succeeded
        """
        logger.info(f"Installing dependencies for {server_type} server at {server_path}")

        try:
            if server_type == 'python':
                return await self._install_python_deps(server_path)
            elif server_type == 'node':
                return await self._install_node_deps(server_path)
            else:
                raise ValueError(f"Invalid server type: {server_type}")
        except Exception as e:
            logger.error(f"Failed to install dependencies: {str(e)}")
            return False

    async def _install_python_deps(self, server_path: str) -> bool:
        """Install Python dependencies."""
        path = Path(server_path)
        
        # Check for requirements.txt
        requirements_path = path / 'requirements.txt'
        if requirements_path.exists():
            try:
                process = await asyncio.create_subprocess_exec(
                    'pip', 'install', '-r', str(requirements_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(path)
                )
                await asyncio.wait_for(process.wait(), timeout=self.install_timeout)
                return process.returncode == 0
            except Exception as e:
                logger.error(f"Failed to install from requirements.txt: {str(e)}")
                return False

        # Check for poetry
        pyproject_path = path / 'pyproject.toml'
        if pyproject_path.exists():
            try:
                # Install dependencies with poetry
                process = await asyncio.create_subprocess_exec(
                    'poetry', 'install',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(path)
                )
                await asyncio.wait_for(process.wait(), timeout=self.install_timeout)
                return process.returncode == 0
            except Exception as e:
                logger.error(f"Failed to install with poetry: {str(e)}")
                return False

        logger.warning("No Python dependency files found")
        return True  # No dependencies to install is not a failure

    async def _install_node_deps(self, server_path: str) -> bool:
        """Install Node.js dependencies."""
        path = Path(server_path)
        package_json = path / 'package.json'

        if not package_json.exists():
            logger.warning("No package.json found")
            return True  # No dependencies to install is not a failure

        try:
            # Install dependencies with npm
            process = await asyncio.create_subprocess_exec(
                'npm', 'install',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(path)
            )
            await asyncio.wait_for(process.wait(), timeout=self.install_timeout)
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Failed to install npm dependencies: {str(e)}")
            return False