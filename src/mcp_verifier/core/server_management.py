"""MCP server management functionality."""
import asyncio
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class MCPServerConfig:
    """Manages MCP server configurations."""
    
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_config()
        
    def load_config(self):
        """Load configuration from file."""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {"servers": {}}
            self.save_config()
            
    def save_config(self):
        """Save configuration to file."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
            
    def add_server(self, name: str, config: dict):
        """Add or update server configuration."""
        self.config["servers"][name] = config
        self.save_config()
        
    def remove_server(self, name: str):
        """Remove server configuration."""
        if name in self.config["servers"]:
            del self.config["servers"][name]
            self.save_config()
            
    def get_server(self, name: str) -> Optional[dict]:
        """Get server configuration."""
        return self.config["servers"].get(name)
        
    def list_servers(self) -> List[dict]:
        """List all configured servers."""
        return [
            {"name": name, **config}
            for name, config in self.config["servers"].items()
        ]


class ServerStorageManager:
    """Manages storage of verified servers."""
    
    def __init__(self, storage_root: Path):
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        
    async def store_server(self, zip_path: Path, server_name: str) -> Path:
        """Extract and store server files."""
        server_path = self.storage_root / server_name
        
        # Clean existing files if any
        if server_path.exists():
            shutil.rmtree(server_path)
            
        # Create server directory
        server_path.mkdir(parents=True)
        
        # Extract files
        shutil.unpack_archive(str(zip_path), str(server_path))
        
        return server_path
        
    def get_server_path(self, server_name: str) -> Optional[Path]:
        """Get path to stored server."""
        server_path = self.storage_root / server_name
        return server_path if server_path.exists() else None
        
    def clean_server(self, server_name: str):
        """Remove stored server files."""
        server_path = self.storage_root / server_name
        if server_path.exists():
            shutil.rmtree(server_path)


class ServerProcessManager:
    """Manages MCP server processes."""
    
    def __init__(self, config_manager: MCPServerConfig):
        self.config_manager = config_manager
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        
    async def start_server(self, server_name: str) -> bool:
        """Start MCP server process."""
        config = self.config_manager.get_server(server_name)
        if not config:
            return False
            
        server_path = Path(config["path"])
        server_type = config["type"]
        
        try:
            if server_type == "python":
                main_file = next(server_path.glob("*.py"))
                proc = await asyncio.create_subprocess_exec(
                    "python",
                    str(main_file),
                    cwd=str(server_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:  # node
                proc = await asyncio.create_subprocess_exec(
                    "node",
                    "index.js",
                    cwd=str(server_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
            # Wait briefly to check if process stays up
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
                logger.error(f"Server {server_name} failed to start")
                return False
            except asyncio.TimeoutError:
                # Process is still running after 1 second
                self.processes[server_name] = proc
                return True
                
        except Exception as e:
            logger.error(f"Error starting server {server_name}: {e}")
            return False
            
    async def stop_server(self, server_name: str):
        """Stop MCP server process."""
        if server_name in self.processes:
            proc = self.processes[server_name]
            try:
                proc.terminate()
                await proc.wait()
            except:
                proc.kill()
            finally:
                del self.processes[server_name]
                
    async def restart_server(self, server_name: str) -> bool:
        """Restart MCP server process."""
        await self.stop_server(server_name)
        return await self.start_server(server_name)
        
    def is_running(self, server_name: str) -> bool:
        """Check if server is running."""
        return server_name in self.processes and self.processes[server_name].returncode is None


class VerificationHandler:
    """Handles server verification and registration."""
    
    def __init__(self,
                 config_manager: MCPServerConfig,
                 storage_manager: ServerStorageManager,
                 process_manager: ServerProcessManager):
        self.config_manager = config_manager
        self.storage_manager = storage_manager
        self.process_manager = process_manager

    async def handle_verification(self,
                                  zip_path: Path,
                                  description: str,
                                  server_name: str) -> 'VerificationResult':
        """Complete verification flow including configuration."""
        from .verification import VerificationGraph
        from .models import SecurityIssue
        from .upload_handler import UploadConfig

        # 1. Verify server
        verifier = VerificationGraph(UploadConfig())
        result = await verifier.verify(str(zip_path), description)

        if result.approved:
            try:
                # Store server files (if needed)
                server_path = await self.storage_manager.store_server(
                    zip_path,
                    server_name
                )

                # Determine server type
                is_python = any(server_path.glob("*.py"))

                # Add to configuration
                self.config_manager.add_server(server_name, {
                    "path": str(server_path),
                    "description": description,
                    "type": "python" if is_python else "node"
                })

            except Exception as e:
                logger.error(f"Error configuring server {server_name}: {e}")
                result.approved = False
                result.security_issues.append(
                    SecurityIssue(
                        severity="ERROR",
                        location="server_configuration",
                        description=f"Failed to configure server: {str(e)}"
                    )
                )

        return result