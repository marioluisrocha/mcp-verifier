"""MCP protocol utilities."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ToolDefinition:
    """MCP tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str

class MCPUtils:
    """Utilities for working with MCP protocol."""
    
    @staticmethod
    def convert_tool_to_openai_function(tool: ToolDefinition) -> Dict[str, Any]:
        """Convert MCP tool definition to OpenAI function format.
        
        Args:
            tool: Tool definition
            
        Returns:
            Function definition in OpenAI format
        """
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": tool.input_schema.get("properties", {}),
                "required": tool.input_schema.get("required", [])
            }
        }
        
    @staticmethod
    def find_server_for_tool(tool_name: str,
                            server_tools: Dict[str, List[ToolDefinition]]) -> Optional[str]:
        """Find server that provides a specific tool.
        
        Args:
            tool_name: Name of the tool
            server_tools: Dictionary mapping server names to their tools
            
        Returns:
            Server name or None if not found
        """
        for server_name, tools in server_tools.items():
            if any(t.name == tool_name for t in tools):
                return server_name
        return None