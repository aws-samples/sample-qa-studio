import random
import string
from datetime import datetime
from typing import Dict, List
from models import ExecutionVariables


class TemplateParser:
    """Template parser that mimics the Go template functionality"""
    
    def __init__(self, execution_id: str, created_at: str, execution_variables: ExecutionVariables = None):
        self.execution_id = execution_id
        self.created_at = created_at
        self.execution_variables = execution_variables
        self.variables = self._build_variables_dict(execution_variables)
    
    def _build_variables_dict(self, execution_variables: ExecutionVariables = None) -> Dict[str, str]:
        """Build variables dictionary from execution variables plus built-in variables"""
        variables = {}
        
        # Add execution variables if provided
        if execution_variables:
            for var in execution_variables.variables:
                variables[var.key] = var.value
            
            # Add runtime variables if they exist
            if execution_variables.runtime_variables:
                for var in execution_variables.runtime_variables:
                    variables[var.key] = var.value
        
        # Add built-in variables (matching Go implementation)
        variables["UniqueID"] = self._generate_unique_id()
        variables["Time"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
        variables["ExecutionID"] = self.execution_id
        variables["CreatedAt"] = self.created_at
        
        return variables
    
    def _generate_unique_id(self, length: int = 5) -> str:
        """Generate a random string for unique ID (matching Go implementation)"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))
    
    def parse_instruction(self, instruction: str) -> str:
        """Parse instruction template and replace variables (matching Go template syntax)"""
        parsed = instruction
        
        for key, value in self.variables.items():
            # Replace {{key}} with value (Go template syntax)
            parsed = parsed.replace(f"{{{{{key}}}}}", value)
        
        return parsed
    
    def parse_steps(self, steps: List) -> List:
        """Parse all step instructions and validation values with template variables"""
        parsed_steps = []
        
        for step in steps:
            # Create a copy of the step with parsed instruction
            parsed_step = step
            parsed_step.instruction = self.parse_instruction(step.instruction)
            
            # Parse validation value if it's a validation step
            if step.step_type == "validation" and hasattr(step, 'validation_value') and step.validation_value:
                parsed_step.validation_value = self.parse_instruction(step.validation_value)
            
            parsed_steps.append(parsed_step)
        
        return parsed_steps
    
    def parse_single_step(self, step) -> object:
        """Parse a single step with current variable context"""
        # Create a copy of the step with parsed instruction
        parsed_step = step
        parsed_step.instruction = self.parse_instruction(step.instruction)
        
        # Parse validation value if it's a validation step
        if step.step_type == "validation" and hasattr(step, 'validation_value') and step.validation_value:
            parsed_step.validation_value = self.parse_instruction(step.validation_value)
        
        return parsed_step
    
    def add_runtime_variable(self, key: str, value: str):
        """Add a runtime variable and update the variables dictionary"""
        # Create execution_variables if it doesn't exist
        if not self.execution_variables:
            from models import ExecutionVariables
            self.execution_variables = ExecutionVariables(
                pk=f'EXECUTION#{self.execution_id}',
                sk='EXECUTION_VARIABLES',
                variables=[],
                runtime_variables=[],
                created_at=self.created_at
            )
        
        if not self.execution_variables.runtime_variables:
            self.execution_variables.runtime_variables = []
        
        # Validate variable name (basic validation)
        if not key or not isinstance(key, str):
            raise ValueError(f"Invalid variable name: {key}")
        
        # Check for conflicts with built-in variables
        builtin_vars = ["UniqueID", "Time", "ExecutionID", "CreatedAt"]
        if key in builtin_vars:
            raise ValueError(f"Cannot override built-in variable: {key}")
        
        # Add or update the runtime variable
        for var in self.execution_variables.runtime_variables:
            if var.key == key:
                var.value = value
                break
        else:
            from models import KeyValuePair
            self.execution_variables.runtime_variables.append(KeyValuePair(key=key, value=value))
        
        # Rebuild variables dictionary to include new runtime variable
        self.variables = self._build_variables_dict(self.execution_variables)
    
    def get_runtime_variables(self) -> List:
        """Get current runtime variables"""
        if self.execution_variables and self.execution_variables.runtime_variables:
            return self.execution_variables.runtime_variables
        return []
    
    def get_all_variables(self) -> Dict[str, str]:
        """Get all available variables (predefined + runtime + built-in)"""
        return self.variables.copy()
    
    def get_runtime_variables_dict(self) -> Dict[str, str]:
        """Get runtime variables as a dictionary for easy access"""
        runtime_vars_dict = {}
        if self.execution_variables and self.execution_variables.runtime_variables:
            for var in self.execution_variables.runtime_variables:
                runtime_vars_dict[var.key] = var.value
        return runtime_vars_dict
    
    def log_available_variables(self, logger):
        """Log all available variables for debugging"""
        logger.info("Available variables:")
        for key, value in self.variables.items():
            # Truncate long values for logging
            display_value = value[:50] + "..." if len(value) > 50 else value
            logger.info(f"  {key} = {display_value}")