"""Security analysis node for MCP server verification."""

from typing import List
import logging
from langchain_core.messages import HumanMessage, AIMessage
from langchain_anthropic import ChatAnthropic

from ..core.models import VerificationState, SecurityIssue

logger = logging.getLogger(__name__)

SECURITY_PROMPT = """Analyze this MCP server code for security issues. Focus on:

1. Command injection vulnerabilities
2. Unsafe file operations
3. Insecure dependencies
4. Network security risks
5. Resource abuse potential (CPU, memory, disk)
6. Input validation
7. Authentication and authorization
8. Secrets handling

Format each issue as:
- Severity: (high/medium/low)
- Description: (detailed explanation)
- Location: (file and line number)
- Recommendation: (how to fix)

Code to analyze:
{code}
"""

class SecurityAnalyzer:
    """Analyzes MCP server code for security vulnerabilities."""
    
    def __init__(self):
        self.llm = ChatAnthropic(model="claude-3-sonnet-20240229")
        
    async def analyze(self, state: VerificationState) -> VerificationState:
        """
        Analyze server code for security issues.
        
        Args:
            state: Current verification state
            
        Returns:
            Updated state with security analysis results
        """
        logger.info("Starting security analysis")
        state.current_stage = "security_check"
        
        try:
            # Prepare code for analysis
            code_contents = []
            for file in state.files.values():
                code_contents.append(f"=== {file.path} ===\n{file.content}\n")
                
            code_text = "\n".join(code_contents)
            
            # Query LLM for security analysis
            messages = [
                HumanMessage(content=SECURITY_PROMPT.format(code=code_text))
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # Parse security issues from response
            issues = self._parse_security_issues(response.content)
            state.security_issues = issues
            
            logger.info(f"Security analysis complete. Found {len(issues)} issues.")
            return state
            
        except Exception as e:
            logger.error(f"Security analysis failed: {str(e)}")
            raise
            
    def _parse_security_issues(self, response: str) -> List[SecurityIssue]:
        """Parse security issues from LLM response."""
        issues = []
        current_issue = {}
        
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('- Severity:'):
                # Save previous issue if exists
                if current_issue and len(current_issue) == 4:
                    try:
                        issues.append(SecurityIssue(**current_issue))
                    except Exception as e:
                        logger.warning(f"Failed to parse security issue: {str(e)}")
                current_issue = {}
                current_issue['severity'] = line.split(':')[1].strip().lower()
                
            elif line.startswith('- Description:'):
                current_issue['description'] = line.split(':')[1].strip()
                
            elif line.startswith('- Location:'):
                current_issue['location'] = line.split(':')[1].strip()
                
            elif line.startswith('- Recommendation:'):
                current_issue['recommendation'] = line.split(':')[1].strip()
                
        # Add last issue
        if current_issue and len(current_issue) == 4:
            try:
                issues.append(SecurityIssue(**current_issue))
            except Exception as e:
                logger.warning(f"Failed to parse security issue: {str(e)}")
                
        return issues