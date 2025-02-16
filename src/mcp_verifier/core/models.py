"""Core data models for MCP server verification."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ServerFile(BaseModel):
    """Represents a file in the MCP server codebase."""
    
    path: str = Field(description="Path to the file relative to server root")
    content: str = Field(description="File content")
    file_type: str = Field(description="File type/extension (e.g., py, js, json)")


class SecurityIssue(BaseModel):
    """Represents a security issue found during verification."""
    
    severity: str = Field(
        description="Issue severity (high, medium, low)",
        pattern="^(high|medium|low)$"
    )
    description: str = Field(description="Detailed description of the issue")
    location: str = Field(description="File and line number where issue was found")
    recommendation: str = Field(description="Recommended fix for the issue")


class GuidelineViolation(BaseModel):
    """Represents a violation of MCP community guidelines."""
    
    rule: str = Field(description="The guideline rule that was violated")
    description: str = Field(description="Description of the violation")
    impact: str = Field(description="Impact of the violation on server operation")


class VerificationState(BaseModel):
    """Represents the current state of the verification process."""
    
    files: Dict[str, ServerFile] = Field(
        default_factory=dict,
        description="Map of file paths to their contents"
    )
    user_description: str = Field(
        default_factory=str,
        description="User-provided server description"
    )
    server_path: Optional[str] = Field(
        default=str,
        description="Path to the server directory"
    )
    security_issues: List[SecurityIssue] = Field(
        default_factory=list,
        description="List of found security issues"
    )
    guideline_violations: List[GuidelineViolation] = Field(
        default_factory=list,
        description="List of guideline violations"
    )
    description_match: float = Field(
        default=0.0,
        description="Similarity score between implementation and description",
        ge=0.0,
        le=1.0
    )
    current_stage: str = Field(
        default="init",
        description="Current verification stage"
    )
    status: str = Field(
        default="pending",
        description="Overall verification status",
        pattern="^(pending|approved|rejected)$"
    )


class VerificationResult(BaseModel):
    """Final result of the verification process."""
    
    approved: bool = Field(description="Whether the server passed verification")
    security_issues: List[SecurityIssue] = Field(
        default_factory=list,
        description="List of security issues found"
    )
    guideline_violations: List[GuidelineViolation] = Field(
        default_factory=list,
        description="List of guideline violations found"
    )
    description_match: float = Field(
        description="Similarity score between implementation and description",
        ge=0.0,
        le=1.0
    )
    
    @property
    def has_issues(self) -> bool:
        """Check if any issues were found during verification."""
        return bool(self.security_issues or self.guideline_violations or self.description_match < 0.8)
        
    def get_summary(self) -> str:
        """Get a human-readable summary of the verification result."""
        status = "PASSED" if self.approved else "FAILED"
        return f"""
Verification {status}

Security Issues: {len(self.security_issues)}
Guideline Violations: {len(self.guideline_violations)}
Description Match: {self.description_match:.1%}
""".strip()