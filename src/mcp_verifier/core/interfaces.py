"""Interfaces for MCP server verification components."""

from abc import ABC, abstractmethod
from typing import Protocol, TypeVar, Generic, Awaitable

from src.mcp_verifier.core.models import VerificationState

T = TypeVar('T')

class VerificationNode(Protocol):
    """Protocol for verification nodes in the graph."""
    
    async def analyze(self, state: VerificationState) -> VerificationState:
        """
        Analyze the server state and update verification state.
        
        Args:
            state: Current verification state
            
        Returns:
            Updated verification state
        """
        ...

class ProcessManager(ABC):
    """Abstract base class for server process management."""
    
    @abstractmethod
    async def start_server(self, main_file: str) -> bool:
        """
        Start the MCP server and verify it's running correctly.
        
        Args:
            main_file: Path to server's main file
            
        Returns:
            True if server started successfully
        """
        pass
        
    @abstractmethod
    async def stop_server(self) -> None:
        """Stop the MCP server and cleanup resources."""
        pass
        
    @abstractmethod
    async def is_healthy(self) -> bool:
        """
        Check if the server is running and healthy.
        
        Returns:
            True if server is responding normally
        """
        pass

class Cache(Generic[T]):
    """Interface for caching verification results."""
    
    @abstractmethod
    async def get(self, key: str) -> T:
        """
        Get cached value for key.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value
            
        Raises:
            KeyError: If key not found
        """
        pass
        
    @abstractmethod
    async def set(self, key: str, value: T) -> None:
        """
        Set cache value for key.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        pass
        
    @abstractmethod
    async def invalidate(self, key: str) -> None:
        """
        Remove key from cache.
        
        Args:
            key: Cache key to remove
        """
        pass

class VerificationEvent(Protocol):
    """Protocol for verification events."""
    
    async def emit(self, event_type: str, data: dict) -> None:
        """
        Emit a verification event.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        ...