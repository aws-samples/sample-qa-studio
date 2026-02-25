# Bedrock AgentCore Browser Tool VPC Implementation Specs

## VPC Architecture Requirements

### Network Setup
- **Private subnets**: 2+ in different AZs (required for high availability)
- **Public subnet**: 1+ with NAT Gateway for internet access
- **Internet Gateway**: Attached to VPC
- **Route table**: Private subnets → NAT Gateway (0.0.0.0/0)

### Supported Availability Zone IDs by Region
```
us-east-1:     use1-az1, use1-az2, use1-az4
us-west-2:     usw2-az1, usw2-az2, usw2-az3
eu-west-1:     euw1-az1, euw1-az2, euw1-az3
us-east-2:     use2-az1, use2-az2, use2-az3
ap-southeast-2: apse2-az1, apse2-az2, apse2-az3
```

## Security Group Configuration

### Browser Tool Security Group
```json
{
  "outbound_rules": [
    {
      "protocol": "TCP",
      "port": 443,
      "destination": "0.0.0.0/0",
      "description": "HTTPS for web browsing"
    },
    {
      "protocol": "TCP", 
      "port": 80,
      "destination": "0.0.0.0/0",
      "description": "HTTP for web browsing"
    }
  ],
  "inbound_rules": []
}
```

### Private Resource Access (Optional)
```json
{
  "browser_sg_outbound": [
    {
      "protocol": "TCP",
      "port": 3306,
      "destination": "sg-database-id",
      "description": "MySQL database access"
    }
  ],
  "database_sg_inbound": [
    {
      "protocol": "TCP",
      "port": 3306,
      "source": "sg-browser-id",
      "description": "Allow Browser Tool access"
    }
  ]
}
```

## VPC Endpoints (No Internet Access)

Required endpoints if VPC has no internet access:
```
com.amazonaws.<region>.ecr.dkr    # ECR Docker
com.amazonaws.<region>.ecr.api    # ECR API
com.amazonaws.<region>.s3         # S3 Gateway
com.amazonaws.<region>.logs       # CloudWatch Logs
```

## IAM Execution Role

### Minimal Required Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream", 
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

## Implementation Commands

### AWS CLI
```bash
aws bedrock-agentcore-control create-browser \
  --name "vpc-browser" \
  --network-configuration '{
    "networkMode": "VPC",
    "networkModeConfig": {
      "subnets": ["subnet-private1", "subnet-private2"],
      "securityGroups": ["sg-browser-tool"]
    }
  }' \
  --execution-role-arn "arn:aws:iam::ACCOUNT:role/BrowserExecutionRole"
```

### Python SDK
```python
import boto3

client = boto3.client(
    'bedrock-agentcore-control', 
    region_name="us-east-1",
    endpoint_url="https://bedrock-agentcore-control.us-east-1.amazonaws.com"
)

response = client.create_browser(
    name="vpc-browser",
    networkConfiguration={
        'networkMode': 'VPC',
        'networkModeConfig': {
            'subnets': ['subnet-private1', 'subnet-private2'],
            'securityGroups': ['sg-browser-tool']
        }
    },
    executionRoleArn="arn:aws:iam::ACCOUNT:role/BrowserExecutionRole"
)
```

## Critical Notes

⚠️ **Browser Tool must be placed in private subnets with NAT Gateway**
- Public subnets do NOT provide internet access
- NAT Gateway is required for outbound internet connectivity

⚠️ **Service-Linked Role**
- AWS automatically creates `AWSServiceRoleForBedrockAgentCoreNetwork`
- Manages ENIs in your VPC

⚠️ **Testing Connectivity**
```bash
# Test internet access via Code Interpreter
awscurl -X POST \
  "https://bedrock-agentcore.<region>.amazonaws.com/code-interpreters/<id>/tools/invoke" \
  -d '{"name": "executeCommand", "arguments": {"command": "curl amazon.com"}}'
```
