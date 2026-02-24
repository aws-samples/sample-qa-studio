import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";

interface ValidationResultProps {
  validationType: string;
  validationOperator: string;
  validationValue: string;
  actualValue: string;
  status: string;
}

function getOperatorDisplay(operator: string): string {
  const operatorMap: { [key: string]: string } = {
    'exact': 'Equals',
    'exact_case_insensitive': 'Equals (case insensitive)',
    'contains': 'Contains',
    'contains_case_insensitive': 'Contains (case insensitive)',
    'not_equal': 'Not Equal',
    'equals': 'Equals',
    'greater_then': 'Greater Than',
    'less_then': 'Less Than',
    'greater_or_equal_then': 'Greater Than or Equal',
    'less_or_equal_then': 'Less Than or Equal'
  };

  return operatorMap[operator] || operator;
}

function getValidationTypeDisplay(type: string): string {
  const typeMap: { [key: string]: string } = {
    'bool': 'Boolean',
    'string': 'Text',
    'number': 'Number'
  };

  return typeMap[type] || type;
}

function getComparisonSymbol(operator: string): string {
  const symbolMap: { [key: string]: string } = {
    'exact': '=',
    'exact_case_insensitive': '≈',
    'contains': '∋',
    'contains_case_insensitive': '∋',
    'not_equal': '≠',
    'equals': '=',
    'greater_then': '>',
    'less_then': '<',
    'greater_or_equal_then': '≥',
    'less_or_equal_then': '≤'
  };

  return symbolMap[operator] || '?';
}

export default function ValidationResult({
  validationType,
  validationOperator,
  validationValue,
  actualValue,
  status
}: ValidationResultProps) {
  const isSuccess = status === 'success';

  return (
    <SpaceBetween direction="vertical" size="xs">
      <Box>
        <span style={{
          color: '#5f6b7a',
          fontSize: '11px',
          fontWeight: 'normal'
        }}>
          {getValidationTypeDisplay(validationType)} ({getOperatorDisplay(validationOperator)})
        </span>
      </Box>

      <Box>
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '16px',
          fontSize: '14px',
          fontFamily: 'monospace'
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '2px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{
                color: isSuccess ? '#037f0c' : '#d91515',
                fontWeight: 'bold'
              }}>
                {actualValue}
              </span>
              <span style={{ color: '#5f6b7a', fontSize: '16px' }}>
                {getComparisonSymbol(validationOperator)}
              </span>
              <span style={{ color: '#879596' }}>
                {validationValue}
              </span>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <span style={{ color: '#5f6b7a', fontSize: '10px' }}>Actual</span>
              <span style={{ color: '#5f6b7a', fontSize: '11px', visibility: 'hidden' }}>
                {getComparisonSymbol(validationOperator)}
              </span>
              <span style={{ color: '#5f6b7a', fontSize: '10px' }}>Expected</span>
            </div>
          </div>
        </div>
      </Box>


    </SpaceBetween>
  );
}