"""Guidelines compliance analyzer for MCP server verification."""

from typing import List
import logging

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from langchain_anthropic import ChatAnthropic

from src.mcp_verifier.core.models import VerificationState, GuidelineViolation

logger = logging.getLogger(__name__)

GUIDELINES_PROMPT = """Analyze this MCP server implementation for compliance with community guidelines:

Key Guidelines:
1. Error Handling
   - Proper error messages
   - Error status codes
   - Error propagation

2. Rate Limiting
   - Request rate limits
   - Resource usage limits
   - Concurrent connection limits

3. Response Format
   - Standard MCP response structure
   - Proper content types
   - Valid JSON schemas

4. Resource Management
   - Memory management
   - File handle cleanup
   - Connection pooling
   - Timeout handling

5. Documentation
   - API documentation
   - Usage examples
   - Error documentation

For each violation, provide:
- Rule: (guideline rule violated)
- Description: (detailed explanation)
- Impact: (effect on server operation)

Server implementation:
{code}
"""

class GuidelinesAnalyzer:
    """Analyzes MCP server for community guidelines compliance."""
    
    def __init__(self):
        self.llm = ChatAnthropic(model="claude-3-sonnet-20240229")
        
    async def analyze(self, state: VerificationState) -> VerificationState:
        """
        Analyze server for guidelines compliance.
        
        Args:
            state: Current verification state
            
        Returns:
            Updated state with guidelines analysis results
        """
        logger.info("Starting guidelines compliance analysis")
        state.current_stage = "guideline_check"
        
        try:
            # Prepare code for analysis
            code_contents = []
            for file in state.files.values():
                code_contents.append(f"=== {file.path} ===\n{file.content}\n")
                
            code_text = "\n".join(code_contents)
            
            # Query LLM for guidelines analysis
            messages = [
                HumanMessage(content=GUIDELINES_PROMPT.format(code=code_text))
            ]
            
            response = await self.llm.ainvoke(messages)
            
            # Parse violations from response
            violations = self._parse_violations(response.content)
            state.guideline_violations = violations
            
            logger.info(f"Guidelines analysis complete. Found {len(violations)} violations.")
            return state
            
        except Exception as e:
            logger.error(f"Guidelines analysis failed: {str(e)}")
            raise
            
    def _parse_violations(self, response: str) -> List[GuidelineViolation]:
        """Parse guideline violations from LLM response."""
        violations = []
        current_violation = {}
        
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('- Rule:'):
                # Save previous violation if exists
                if current_violation and len(current_violation) == 3:
                    try:
                        violations.append(GuidelineViolation(**current_violation))
                    except Exception as e:
                        logger.warning(f"Failed to parse guideline violation: {str(e)}")
                current_violation = {}
                split_lines = list(line.split(':'))
                if len(split_lines) > 1:
                    current_violation['rule'] = split_lines[1].strip()
                
            elif line.startswith('- Description:'):
                split_lines = list(line.split(':'))
                if len(split_lines) > 1:
                    current_violation['description'] = split_lines[1].strip()
                
            elif line.startswith('- Impact:'):
                split_lines = list(line.split(':'))
                if len(split_lines) > 1:
                    current_violation['impact'] = split_lines[1].strip()
                
        # Add last violation
        if current_violation and len(current_violation) == 3:
            try:
                violations.append(GuidelineViolation(**current_violation))
            except Exception as e:
                logger.warning(f"Failed to parse guideline violation: {str(e)}")
                
        return violations
        
    def get_severity_score(self, violations: List[GuidelineViolation]) -> float:
        """
        Calculate overall severity score of violations.
        
        Returns:
            Score between 0.0 (critical violations) and 1.0 (no violations)
        """
        if not violations:
            return 1.0
            
        # Count violations by impact
        critical = sum(1 for v in violations if 'critical' in v.impact.lower())
        major = sum(1 for v in violations if 'major' in v.impact.lower())
        minor = sum(1 for v in violations if 'minor' in v.impact.lower())
        
        # Weight violations
        score = 1.0
        score -= critical * 0.3  # Critical violations have high impact
        score -= major * 0.15    # Major violations have medium impact
        score -= minor * 0.05    # Minor violations have low impact
        
        return max(0.0, score)  # Ensure score is not negative