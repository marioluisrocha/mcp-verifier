"""MCP Session Management."""

import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@dataclass
class ServerConnection:
    """Represents a connection to an MCP server."""
    name: str
    session: ClientSession
    tools: List[dict]
    exit_stack: AsyncExitStack

class SessionManager:
    """Manages MCP server sessions."""
    
    def __init__(self):
        self.connections: Dict[str, ServerConnection] = {}
        
    async def connect_server(self, name: str, script_path: str) -> ServerConnection:
        """Connect to an MCP server.
        
        Args:
            name: Unique name for this server connection
            script_path: Path to server script
        """
        # Validate server type
        if not (script_path.endswith('.py') or script_path.endswith('.js')):
            raise ValueError("Server script must be a .py or .js file")
            
        # Setup server parameters
        command = "python" if script_path.endswith('.py') else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[script_path],
            env=None
        )
        
        # Create exit stack for resource management
        exit_stack = AsyncExitStack()
        
        try:
            # Setup stdio transport
            stdio_transport = await exit_stack.enter_async_context(stdio_client(server_params))
            stdio, write = stdio_transport
            
            # Create and initialize session
            session = await exit_stack.enter_async_context(ClientSession(stdio, write))
            await session.initialize()
            
            # Get available tools
            tools_response = await session.list_tools()
            tools = [{
                'name': tool.name,
                'description': tool.description,
                'input_schema': tool.inputSchema
            } for tool in tools_response.tools]
            
            # Create connection object
            connection = ServerConnection(
                name=name,
                session=session,
                tools=tools,
                exit_stack=exit_stack
            )
            
            # Store connection
            self.connections[name] = connection
            
            return connection
            
        except Exception as e:
            await exit_stack.aclose()
            raise RuntimeError(f"Failed to connect to server: {str(e)}")
            
    async def disconnect_server(self, name: str):
        """Disconnect from a server."""
        if name in self.connections:
            connection = self.connections[name]
            await connection.exit_stack.aclose()
            del self.connections[name]
            
    async def call_tool(self, server_name: str, tool_name: str, **tool_args):
        """Call a tool on a specific server."""
        if server_name not in self.connections:
            raise ValueError(f"No connection to server: {server_name}")
            
        connection = self.connections[server_name]
        return await connection.session.call_tool(tool_name, tool_args)
        
    def get_all_tools(self) -> Dict[str, List[dict]]:
        """Get all available tools grouped by server."""
        return {name: conn.tools for name, conn in self.connections.items()}
        
    async def cleanup(self):
        """Clean up all connections."""
        for name in list(self.connections.keys()):
            await self.disconnect_server(name)
