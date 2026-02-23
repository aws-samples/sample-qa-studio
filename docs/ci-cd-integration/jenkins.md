# Jenkins Integration

This guide shows how to integrate the Nova Act QA Studio CI/CD Runner into your Jenkins pipelines for automated testing.

## Overview

The CI/CD runner can be integrated into Jenkins pipelines to execute test suites automatically on code changes, pull requests, or scheduled intervals. The runner uses OAuth client credentials for authentication and reports test results via exit codes.

## Prerequisites

Before setting up Jenkins integration, ensure you have:

1. **Jenkins with Docker**: Jenkins server with Docker installed and Docker Pipeline plugin
2. **OAuth Client**: Created via the Nova Act QA Studio platform with required scopes:
   - `api/suite.read` - Read test suite definitions
   - `api/suite.write` - Execute test suites
   - `api/execution.write` - Create and update execution records
3. **Test Suite ID**: UUID of the test suite to execute (found in platform UI)

## Quick Start

Basic declarative pipeline that runs tests on every build:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

## Setup Instructions

### Step 1: Install Required Plugins

Install the following Jenkins plugins:

1. **Docker Pipeline Plugin**: For Docker support in pipelines
   - Navigate to **Manage Jenkins** → **Manage Plugins**
   - Go to **Available** tab
   - Search for "Docker Pipeline"
   - Check the box and click **Install without restart**

2. **Credentials Binding Plugin**: For secure credential management (usually pre-installed)
   - Search for "Credentials Binding"
   - Install if not already present

### Step 2: Create OAuth Client

Create an OAuth client in the Nova Act QA Studio platform:

1. Navigate to **Settings** → **OAuth Clients**
2. Click **Create OAuth Client**
3. Enter a name: `Jenkins - <Project Name>`
4. Select scopes:
   - `api/suite.read`
   - `api/suite.write`
   - `api/execution.write`
5. Click **Create**
6. **Save the client secret** - it will only be shown once!

### Step 3: Configure Jenkins Credentials

Add OAuth credentials as Jenkins credentials:

1. Go to **Manage Jenkins** → **Manage Credentials**
2. Select the appropriate domain (usually "Global")
3. Click **Add Credentials**
4. Add the following credentials:

**OAuth Client ID**:
- **Kind**: Secret text
- **Scope**: Global
- **Secret**: `7abc123def456` (your OAuth client ID)
- **ID**: `oauth-client-id`
- **Description**: OAuth Client ID for Nova Act QA Studio

**OAuth Client Secret**:
- **Kind**: Secret text
- **Scope**: Global
- **Secret**: `secret_xyz789...` (your OAuth client secret)
- **ID**: `oauth-client-secret`
- **Description**: OAuth Client Secret for Nova Act QA Studio

**OAuth Token Endpoint**:
- **Kind**: Secret text
- **Scope**: Global
- **Secret**: `https://domain.auth.us-east-1.amazoncognito.com/oauth2/token`
- **ID**: `oauth-token-endpoint`
- **Description**: OAuth Token Endpoint URL

**API Endpoint**:
- **Kind**: Secret text
- **Scope**: Global
- **Secret**: `https://abc123.execute-api.us-east-1.amazonaws.com/api`
- **ID**: `api-endpoint`
- **Description**: Platform API Base URL

**Security Notes**:
- Credentials are encrypted and masked in console logs
- Never commit credentials to your repository
- Use separate OAuth clients for different projects/environments
- Limit credential access using Jenkins credential domains

### Step 4: Create Pipeline Job

Create a new Jenkins pipeline job:

1. Click **New Item**
2. Enter job name: `QA-Tests`
3. Select **Pipeline**
4. Click **OK**
5. In the pipeline configuration:
   - **Build Triggers**: Configure as needed (e.g., "GitHub hook trigger for GITScm polling")
   - **Pipeline**: Select "Pipeline script" or "Pipeline script from SCM"
   - Paste the pipeline script (see examples below)
6. Click **Save**

### Step 5: Run Pipeline

Trigger the pipeline:

1. Click **Build Now** to run manually
2. Or configure automatic triggers (SCM polling, webhooks, etc.)
3. View console output to see test results

## Declarative Pipeline Examples

### Example 1: Basic Pipeline

Run tests on every build:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
    
    post {
        failure {
            echo 'Tests failed! Check the logs above for details.'
        }
        success {
            echo 'All tests passed!'
        }
    }
}
```

### Example 2: Environment-Specific Testing

Test against staging environment with base URL override:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
        STAGING_BASE_URL = 'https://staging.example.com'
    }
    
    stages {
        stage('Staging Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --base-url ${STAGING_BASE_URL} \
                        --verbose
                '''
            }
        }
    }
}
```

### Example 3: Variable Overrides

Override test variables for different test scenarios:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
        STAGING_BASE_URL = 'https://staging.example.com'
        TEST_API_KEY = credentials('test-api-key')
    }
    
    stages {
        stage('QA Tests with Variables') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --base-url ${STAGING_BASE_URL} \
                        --var username=testuser \
                        --var environment=staging \
                        --var api_key=${TEST_API_KEY} \
                        --verbose
                '''
            }
        }
    }
}
```

### Example 4: Parameterized Pipeline

Allow users to select environment and suite at build time:

```groovy
pipeline {
    agent any
    
    parameters {
        choice(
            name: 'ENVIRONMENT',
            choices: ['staging', 'production'],
            description: 'Environment to test'
        )
        string(
            name: 'SUITE_ID',
            defaultValue: 'suite-123',
            description: 'Test suite ID to execute'
        )
        string(
            name: 'BASE_URL',
            defaultValue: 'https://staging.example.com',
            description: 'Base URL override (optional)'
        )
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${SUITE_ID} \
                        --base-url ${BASE_URL} \
                        --var environment=${ENVIRONMENT} \
                        --verbose
                '''
            }
        }
    }
}
```

### Example 5: Multi-Stage Pipeline

Run smoke tests, then full tests, then deploy:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        SMOKE_SUITE_ID = 'smoke-suite-123'
        FULL_SUITE_ID = 'full-suite-456'
        STAGING_BASE_URL = 'https://staging.example.com'
    }
    
    stages {
        stage('Smoke Tests') {
            steps {
                echo 'Running smoke tests...'
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${SMOKE_SUITE_ID} \
                        --base-url ${STAGING_BASE_URL} \
                        --verbose
                '''
            }
        }
        
        stage('Full Test Suite') {
            steps {
                echo 'Running full test suite...'
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${FULL_SUITE_ID} \
                        --base-url ${STAGING_BASE_URL} \
                        --timeout 7200 \
                        --verbose
                '''
            }
        }
        
        stage('Deploy') {
            steps {
                echo 'Deploying to production...'
                // Add deployment steps here
            }
        }
    }
    
    post {
        failure {
            echo 'Pipeline failed!'
        }
        success {
            echo 'Pipeline completed successfully!'
        }
    }
}
```

### Example 6: Parallel Testing

Test multiple environments in parallel:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('Parallel Tests') {
            parallel {
                stage('Test Staging') {
                    steps {
                        sh '''
                            docker run --rm \
                                -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                                -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                                -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                                -e API_ENDPOINT="${API_ENDPOINT}" \
                                nova-act-cicd-runner:latest \
                                --suite-id ${TEST_SUITE_ID} \
                                --base-url https://staging.example.com \
                                --var environment=staging \
                                --verbose
                        '''
                    }
                }
                
                stage('Test Production') {
                    steps {
                        sh '''
                            docker run --rm \
                                -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                                -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                                -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                                -e API_ENDPOINT="${API_ENDPOINT}" \
                                nova-act-cicd-runner:latest \
                                --suite-id ${TEST_SUITE_ID} \
                                --base-url https://production.example.com \
                                --var environment=production \
                                --verbose
                        '''
                    }
                }
            }
        }
    }
}
```

### Example 7: Conditional Execution

Run different tests based on branch:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
    }
    
    stages {
        stage('Smoke Tests') {
            when {
                anyOf {
                    branch 'develop'
                    branch 'main'
                }
            }
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id smoke-suite-123 \
                        --verbose
                '''
            }
        }
        
        stage('Full Tests') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id full-suite-456 \
                        --timeout 7200 \
                        --verbose
                '''
            }
        }
    }
}
```

### Example 8: Extended Timeout for Large Suites

Increase timeout for long-running test suites:

```groovy
pipeline {
    agent any
    
    options {
        timeout(time: 3, unit: 'HOURS')  // Jenkins pipeline timeout
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        EXTENDED_SUITE_ID = 'extended-suite-789'
    }
    
    stages {
        stage('Extended Test Suite') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${EXTENDED_SUITE_ID} \
                        --timeout 10800 \
                        --verbose
                '''
            }
        }
    }
}
```

## Scripted Pipeline Examples

For users who prefer scripted pipelines over declarative:

### Basic Scripted Pipeline

```groovy
node {
    def oauthClientId = credentials('oauth-client-id')
    def oauthClientSecret = credentials('oauth-client-secret')
    def oauthTokenEndpoint = credentials('oauth-token-endpoint')
    def apiEndpoint = credentials('api-endpoint')
    def testSuiteId = 'suite-123'
    
    stage('QA Tests') {
        def exitCode = sh(
            script: """
                docker run --rm \
                    -e OAUTH_CLIENT_ID="${oauthClientId}" \
                    -e OAUTH_CLIENT_SECRET="${oauthClientSecret}" \
                    -e OAUTH_TOKEN_ENDPOINT="${oauthTokenEndpoint}" \
                    -e API_ENDPOINT="${apiEndpoint}" \
                    nova-act-cicd-runner:latest \
                    --suite-id ${testSuiteId} \
                    --verbose
            """,
            returnStatus: true
        )
        
        if (exitCode != 0) {
            error("QA tests failed with exit code ${exitCode}")
        }
    }
}
```

### Scripted Pipeline with Error Handling

```groovy
node {
    def oauthClientId = credentials('oauth-client-id')
    def oauthClientSecret = credentials('oauth-client-secret')
    def oauthTokenEndpoint = credentials('oauth-token-endpoint')
    def apiEndpoint = credentials('api-endpoint')
    def testSuiteId = 'suite-123'
    
    try {
        stage('QA Tests') {
            def exitCode = sh(
                script: """
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${oauthClientId}" \
                        -e OAUTH_CLIENT_SECRET="${oauthClientSecret}" \
                        -e OAUTH_TOKEN_ENDPOINT="${oauthTokenEndpoint}" \
                        -e API_ENDPOINT="${apiEndpoint}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${testSuiteId} \
                        --verbose
                """,
                returnStatus: true
            )
            
            if (exitCode == 1) {
                error("Tests failed - one or more test cases did not pass")
            } else if (exitCode == 2) {
                error("Runner error - check authentication or configuration")
            } else if (exitCode != 0) {
                error("Unexpected error with exit code ${exitCode}")
            }
            
            echo "All tests passed!"
        }
    } catch (Exception e) {
        currentBuild.result = 'FAILURE'
        echo "Pipeline failed: ${e.message}"
        throw e
    }
}
```

## Docker Plugin Configuration

### Installing Docker Plugin

1. Navigate to **Manage Jenkins** → **Manage Plugins**
2. Go to **Available** tab
3. Search for "Docker Pipeline"
4. Check the box and click **Install without restart**

### Verifying Docker Availability

Add a verification step to ensure Docker is available:

```groovy
pipeline {
    agent any
    
    stages {
        stage('Verify Docker') {
            steps {
                sh 'docker --version'
                sh 'docker ps'
            }
        }
        
        stage('QA Tests') {
            environment {
                OAUTH_CLIENT_ID = credentials('oauth-client-id')
                OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
                OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
                API_ENDPOINT = credentials('api-endpoint')
                TEST_SUITE_ID = 'suite-123'
            }
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

### Using Docker Agent

Run the entire pipeline inside a Docker container:

```groovy
pipeline {
    agent {
        docker {
            image 'docker:latest'
            args '-v /var/run/docker.sock:/var/run/docker.sock'
        }
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

### Private Docker Registry

If using a private Docker registry:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
        DOCKER_REGISTRY = 'registry.example.com'
        DOCKER_CREDENTIALS = credentials('docker-registry-credentials')
    }
    
    stages {
        stage('Docker Login') {
            steps {
                sh '''
                    echo "${DOCKER_CREDENTIALS_PSW}" | docker login ${DOCKER_REGISTRY} \
                        -u "${DOCKER_CREDENTIALS_USR}" --password-stdin
                '''
            }
        }
        
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        ${DOCKER_REGISTRY}/nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
    
    post {
        always {
            sh 'docker logout ${DOCKER_REGISTRY}'
        }
    }
}
```

## Pipeline Parameters

Jenkins supports parameterized builds for flexible test execution.

### String Parameters

```groovy
pipeline {
    agent any
    
    parameters {
        string(
            name: 'SUITE_ID',
            defaultValue: 'suite-123',
            description: 'Test suite ID to execute'
        )
        string(
            name: 'BASE_URL',
            defaultValue: '',
            description: 'Base URL override (leave empty to use suite default)'
        )
        string(
            name: 'TIMEOUT',
            defaultValue: '3600',
            description: 'Test execution timeout in seconds'
        )
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    def baseUrlArg = params.BASE_URL ? "--base-url ${params.BASE_URL}" : ""
                    sh """
                        docker run --rm \
                            -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                            -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                            -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                            -e API_ENDPOINT="${API_ENDPOINT}" \
                            nova-act-cicd-runner:latest \
                            --suite-id ${params.SUITE_ID} \
                            ${baseUrlArg} \
                            --timeout ${params.TIMEOUT} \
                            --verbose
                    """
                }
            }
        }
    }
}
```

### Choice Parameters

```groovy
pipeline {
    agent any
    
    parameters {
        choice(
            name: 'ENVIRONMENT',
            choices: ['staging', 'production', 'development'],
            description: 'Environment to test against'
        )
        choice(
            name: 'REGION',
            choices: ['us-east-1', 'us-west-2', 'eu-west-1'],
            description: 'AWS region'
        )
        booleanParam(
            name: 'VERBOSE',
            defaultValue: true,
            description: 'Enable verbose logging'
        )
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    def baseUrl = "https://${params.ENVIRONMENT}.example.com"
                    def verboseFlag = params.VERBOSE ? "--verbose" : ""
                    
                    sh """
                        docker run --rm \
                            -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                            -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                            -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                            -e API_ENDPOINT="${API_ENDPOINT}" \
                            nova-act-cicd-runner:latest \
                            --suite-id ${TEST_SUITE_ID} \
                            --base-url ${baseUrl} \
                            --region ${params.REGION} \
                            --var environment=${params.ENVIRONMENT} \
                            ${verboseFlag}
                    """
                }
            }
        }
    }
}
```

### Multi-Select Parameters

```groovy
pipeline {
    agent any
    
    parameters {
        extendedChoice(
            name: 'TEST_SUITES',
            type: 'PT_CHECKBOX',
            value: 'smoke-suite-123,integration-suite-456,e2e-suite-789',
            description: 'Select test suites to run',
            visibleItemCount: 3
        )
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    def suites = params.TEST_SUITES.split(',')
                    for (suite in suites) {
                        echo "Running test suite: ${suite}"
                        sh """
                            docker run --rm \
                                -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                                -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                                -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                                -e API_ENDPOINT="${API_ENDPOINT}" \
                                nova-act-cicd-runner:latest \
                                --suite-id ${suite} \
                                --verbose
                        """
                    }
                }
            }
        }
    }
}
```

**Note**: Multi-select parameters require the "Extended Choice Parameter" plugin.

## Post-Build Actions

Jenkins provides post-build actions to handle different pipeline outcomes.

### Basic Post Actions

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
    
    post {
        always {
            echo 'Pipeline completed (success or failure)'
        }
        success {
            echo 'All tests passed successfully!'
        }
        failure {
            echo 'Tests failed - check logs for details'
        }
        unstable {
            echo 'Build is unstable'
        }
        changed {
            echo 'Pipeline state changed from previous run'
        }
    }
}
```

### Email Notifications

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
    
    post {
        failure {
            emailext(
                subject: "QA Tests Failed: ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                body: """
                    <p>QA tests have failed.</p>
                    <p><b>Job:</b> ${env.JOB_NAME}</p>
                    <p><b>Build Number:</b> ${env.BUILD_NUMBER}</p>
                    <p><b>Build URL:</b> <a href="${env.BUILD_URL}">${env.BUILD_URL}</a></p>
                    <p>Check the console output for details.</p>
                """,
                to: 'team@example.com',
                mimeType: 'text/html'
            )
        }
        success {
            emailext(
                subject: "QA Tests Passed: ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                body: "All QA tests passed successfully!",
                to: 'team@example.com'
            )
        }
    }
}
```

**Note**: Email notifications require the "Email Extension" plugin and SMTP configuration in Jenkins.

### Slack Notifications

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
    
    post {
        failure {
            slackSend(
                color: 'danger',
                message: "QA Tests Failed: ${env.JOB_NAME} - Build #${env.BUILD_NUMBER} (<${env.BUILD_URL}|Open>)",
                channel: '#qa-alerts'
            )
        }
        success {
            slackSend(
                color: 'good',
                message: "QA Tests Passed: ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                channel: '#qa-alerts'
            )
        }
    }
}
```

**Note**: Slack notifications require the "Slack Notification" plugin and Slack workspace configuration.

### Archiving Test Results

Archive console output or test artifacts:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    sh '''
                        docker run --rm \
                            -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                            -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                            -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                            -e API_ENDPOINT="${API_ENDPOINT}" \
                            nova-act-cicd-runner:latest \
                            --suite-id ${TEST_SUITE_ID} \
                            --verbose > test-output.log 2>&1
                    '''
                }
            }
        }
    }
    
    post {
        always {
            archiveArtifacts artifacts: 'test-output.log', allowEmptyArchive: true
        }
    }
}
```

## Build Triggers

Configure when Jenkins should run the pipeline.

### SCM Polling

Poll source control for changes:

```groovy
pipeline {
    agent any
    
    triggers {
        pollSCM('H/5 * * * *')  // Poll every 5 minutes
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

**Cron Syntax**:
- `H/5 * * * *` - Every 5 minutes (H = hash for load distribution)
- `H 2 * * *` - Daily at 2 AM
- `H 0 * * 0` - Weekly on Sunday at midnight

### Scheduled Builds

Run tests on a schedule:

```groovy
pipeline {
    agent any
    
    triggers {
        cron('0 2 * * *')  // Daily at 2 AM
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('Nightly Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --timeout 7200 \
                        --verbose
                '''
            }
        }
    }
}
```

### GitHub Webhook

Trigger on GitHub push events:

1. Install "GitHub" plugin in Jenkins
2. Configure GitHub webhook in repository settings:
   - Payload URL: `https://jenkins.example.com/github-webhook/`
   - Content type: `application/json`
   - Events: Push events, Pull requests

```groovy
pipeline {
    agent any
    
    triggers {
        githubPush()
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

### GitLab Webhook

Trigger on GitLab push events:

1. Install "GitLab" plugin in Jenkins
2. Configure GitLab webhook in project settings:
   - URL: `https://jenkins.example.com/project/<job-name>`
   - Trigger: Push events, Merge request events

```groovy
pipeline {
    agent any
    
    triggers {
        gitlab(triggerOnPush: true, triggerOnMergeRequest: true)
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

### Upstream Job Trigger

Trigger after another job completes:

```groovy
pipeline {
    agent any
    
    triggers {
        upstream(upstreamProjects: 'build-job', threshold: hudson.model.Result.SUCCESS)
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

## Exit Codes and Pipeline Control

The runner uses exit codes to indicate test results, which Jenkins uses to determine pipeline success or failure.

| Exit Code | Meaning | Pipeline Behavior |
|-----------|---------|-------------------|
| `0` | All tests passed | Pipeline succeeds, continues to next stages |
| `1` | One or more tests failed | Pipeline fails, subsequent stages skipped |
| `2` | Runner error (auth, config, API) | Pipeline fails, subsequent stages skipped |

### Fail Pipeline on Test Failure

Default behavior - pipeline fails if tests fail:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --verbose
                '''
            }
        }
    }
}
```

### Continue on Test Failure

Continue pipeline even if tests fail:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                        sh '''
                            docker run --rm \
                                -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                                -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                                -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                                -e API_ENDPOINT="${API_ENDPOINT}" \
                                nova-act-cicd-runner:latest \
                                --suite-id ${TEST_SUITE_ID} \
                                --verbose
                        '''
                    }
                }
            }
        }
        
        stage('Continue Anyway') {
            steps {
                echo 'This stage runs even if tests fail'
            }
        }
    }
}
```

### Custom Handling Based on Exit Code

Handle different exit codes differently:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                script {
                    def exitCode = sh(
                        script: '''
                            docker run --rm \
                                -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                                -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                                -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                                -e API_ENDPOINT="${API_ENDPOINT}" \
                                nova-act-cicd-runner:latest \
                                --suite-id ${TEST_SUITE_ID} \
                                --verbose
                        ''',
                        returnStatus: true
                    )
                    
                    if (exitCode == 0) {
                        echo '✅ All tests passed!'
                    } else if (exitCode == 1) {
                        echo '❌ Tests failed - check logs above'
                        currentBuild.result = 'FAILURE'
                        error('One or more tests failed')
                    } else if (exitCode == 2) {
                        echo '⚠️ Runner error - check configuration'
                        currentBuild.result = 'FAILURE'
                        error('Runner configuration or authentication error')
                    } else {
                        echo "⚠️ Unexpected exit code: ${exitCode}"
                        currentBuild.result = 'FAILURE'
                        error("Unexpected error with exit code ${exitCode}")
                    }
                }
            }
        }
    }
}
```

## Best Practices

### Security

1. **Use Jenkins Credentials**: Store OAuth credentials in Jenkins credential store, never in pipeline code
2. **Credential Domains**: Use credential domains to limit access to specific jobs or folders
3. **Separate OAuth Clients**: Use different OAuth clients for different projects/environments
4. **Minimal Scopes**: Grant only required scopes to OAuth clients
5. **Rotate Credentials**: Rotate OAuth client secrets regularly (every 90 days)
6. **Audit Logs**: Enable Jenkins audit logging to track credential access

### Performance

1. **Parallel Execution**: Use parallel stages to test multiple configurations simultaneously
2. **Conditional Execution**: Use `when` conditions to run tests only when relevant
3. **Docker Image Caching**: Pull and cache Docker images to speed up pipeline execution
4. **Timeout Configuration**: Set appropriate timeouts for large test suites
5. **Agent Labels**: Use agent labels to run jobs on specific nodes with Docker support

### Reliability

1. **Retry Logic**: Add retry configuration for transient failures
2. **Verbose Logging**: Use `--verbose` flag for troubleshooting
3. **Health Checks**: Add smoke tests before running full test suites
4. **Notifications**: Set up notifications for pipeline failures (email, Slack, etc.)
5. **Manual Approval**: Use input steps for production deployments

### Organization

1. **Descriptive Names**: Use clear stage and job names
2. **Comments**: Add comments to explain complex pipeline logic
3. **Shared Libraries**: Create shared libraries for reusable pipeline code
4. **Environment Variables**: Use Jenkins environment variables for configuration
5. **Pipeline Visualization**: Structure stages logically for clear Blue Ocean visualization

### Example: Well-Organized Pipeline

```groovy
// Comprehensive QA testing pipeline with best practices
pipeline {
    agent any
    
    options {
        timeout(time: 2, unit: 'HOURS')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }
    
    parameters {
        choice(
            name: 'ENVIRONMENT',
            choices: ['staging', 'production'],
            description: 'Environment to test'
        )
        booleanParam(
            name: 'RUN_SMOKE_ONLY',
            defaultValue: false,
            description: 'Run only smoke tests'
        )
    }
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        SMOKE_SUITE_ID = 'smoke-suite-123'
        FULL_SUITE_ID = 'full-suite-456'
    }
    
    stages {
        stage('Verify Docker') {
            steps {
                sh 'docker --version'
            }
        }
        
        stage('Smoke Tests') {
            steps {
                echo "Running smoke tests on ${params.ENVIRONMENT}"
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${SMOKE_SUITE_ID} \
                        --var environment=${ENVIRONMENT} \
                        --verbose
                '''
            }
        }
        
        stage('Full Test Suite') {
            when {
                expression { params.RUN_SMOKE_ONLY == false }
            }
            steps {
                echo "Running full test suite on ${params.ENVIRONMENT}"
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${FULL_SUITE_ID} \
                        --var environment=${ENVIRONMENT} \
                        --timeout 7200 \
                        --verbose
                '''
            }
        }
    }
    
    post {
        always {
            echo "Pipeline completed with status: ${currentBuild.result}"
        }
        success {
            echo 'All tests passed successfully!'
        }
        failure {
            echo 'Tests failed - check logs for details'
            emailext(
                subject: "QA Tests Failed: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                body: "Check console output: ${env.BUILD_URL}console",
                to: 'team@example.com'
            )
        }
    }
}
```

## Troubleshooting

### Pipeline Not Triggering

**Problem**: Pipeline doesn't run on SCM changes or webhooks

**Solutions**:
1. Verify webhook is configured correctly in SCM (GitHub, GitLab, etc.)
2. Check Jenkins webhook URL is accessible from internet
3. Verify Jenkins has required plugins installed (GitHub, GitLab, etc.)
4. Check Jenkins system log for webhook errors: **Manage Jenkins** → **System Log**
5. Test webhook manually using SCM webhook test feature

### Authentication Failures

**Problem**: `OAuth authentication failed: 401`

**Solutions**:
1. Verify credentials are set correctly in Jenkins credential store
2. Check credential IDs match exactly in pipeline (case-sensitive)
3. Ensure OAuth client exists and is active in platform
4. Verify OAuth client has required scopes (`api/suite.read`, `api/suite.write`, `api/execution.write`)
5. Check token endpoint URL is correct
6. Test credentials manually using curl:
   ```bash
   curl -X POST "https://domain.auth.region.amazoncognito.com/oauth2/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=client_credentials&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET"
   ```

### Docker Not Available

**Problem**: `docker: command not found` or `Cannot connect to Docker daemon`

**Solutions**:
1. Verify Docker is installed on Jenkins agent: `docker --version`
2. Ensure Jenkins user has permission to run Docker:
   ```bash
   sudo usermod -aG docker jenkins
   sudo systemctl restart jenkins
   ```
3. Check Docker daemon is running: `sudo systemctl status docker`
4. Verify Docker socket permissions: `ls -l /var/run/docker.sock`
5. Use Docker agent if Docker not available on Jenkins master

### Docker Pull Failures

**Problem**: `Unable to find image 'nova-act-cicd-runner:latest'`

**Solutions**:
1. Ensure Docker image is available in registry
2. Add authentication if using private registry (see Docker Plugin Configuration section)
3. Specify full image path including registry URL
4. Pull image manually to verify: `docker pull nova-act-cicd-runner:latest`
5. Check network connectivity from Jenkins agent to Docker registry

### Test Timeouts

**Problem**: Tests timeout before completion

**Solutions**:
1. Increase runner timeout: `--timeout 7200`
2. Increase Jenkins pipeline timeout: `options { timeout(time: 3, unit: 'HOURS') }`
3. Split large test suites into smaller suites
4. Run tests in parallel using parallel stages
5. Check network connectivity and latency

### Credentials Not Available

**Problem**: Credentials are empty or undefined in pipeline

**Solutions**:
1. Verify credentials exist in Jenkins credential store
2. Check credential IDs match exactly (case-sensitive)
3. Ensure credentials are in correct domain (Global or specific folder)
4. Verify pipeline has permission to access credentials
5. Check credential scope is set to "Global" or appropriate domain

### Pipeline Syntax Errors

**Problem**: Pipeline fails with syntax errors

**Solutions**:
1. Use Jenkins Pipeline Syntax Generator: **Pipeline Syntax** link in job configuration
2. Validate Groovy syntax using Jenkins Declarative Directive Generator
3. Check for common issues:
   - Missing quotes around strings
   - Incorrect indentation
   - Missing closing braces
   - Invalid environment variable references
4. Use Jenkins Replay feature to test changes without committing

### Console Output Not Showing

**Problem**: Test output not visible in Jenkins console

**Solutions**:
1. Ensure `--verbose` flag is used for detailed output
2. Remove `--rm` flag temporarily to inspect container logs
3. Redirect output explicitly: `docker run ... 2>&1 | tee output.log`
4. Check Jenkins console output buffer size settings
5. Use `sh` step with `returnStdout: true` to capture output

## Advanced Patterns

### Shared Library for Reusable Code

Create a shared library for common QA test patterns:

**vars/runQATests.groovy**:
```groovy
def call(Map config) {
    def suiteId = config.suiteId ?: error('suiteId is required')
    def baseUrl = config.baseUrl ?: ''
    def timeout = config.timeout ?: '3600'
    def verbose = config.verbose != false
    
    def baseUrlArg = baseUrl ? "--base-url ${baseUrl}" : ""
    def verboseArg = verbose ? "--verbose" : ""
    
    sh """
        docker run --rm \
            -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
            -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
            -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
            -e API_ENDPOINT="${API_ENDPOINT}" \
            nova-act-cicd-runner:latest \
            --suite-id ${suiteId} \
            ${baseUrlArg} \
            --timeout ${timeout} \
            ${verboseArg}
    """
}
```

**Use the shared library**:
```groovy
@Library('qa-shared-library') _

pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
    }
    
    stages {
        stage('QA Tests') {
            steps {
                runQATests(
                    suiteId: 'suite-123',
                    baseUrl: 'https://staging.example.com',
                    timeout: '7200'
                )
            }
        }
    }
}
```

### Blue Ocean Compatibility

The pipeline examples are fully compatible with Jenkins Blue Ocean UI:

1. Install Blue Ocean plugin: **Manage Jenkins** → **Manage Plugins** → Search "Blue Ocean"
2. Access Blue Ocean: Click **Open Blue Ocean** in Jenkins sidebar
3. View pipeline visualization with stages and parallel execution
4. Use Blue Ocean editor for visual pipeline creation

### Multibranch Pipeline

Create a multibranch pipeline for automatic branch detection:

1. Create **New Item** → **Multibranch Pipeline**
2. Configure branch sources (GitHub, GitLab, etc.)
3. Add `Jenkinsfile` to repository root:

```groovy
pipeline {
    agent any
    
    environment {
        OAUTH_CLIENT_ID = credentials('oauth-client-id')
        OAUTH_CLIENT_SECRET = credentials('oauth-client-secret')
        OAUTH_TOKEN_ENDPOINT = credentials('oauth-token-endpoint')
        API_ENDPOINT = credentials('api-endpoint')
        TEST_SUITE_ID = 'suite-123'
    }
    
    stages {
        stage('QA Tests') {
            steps {
                sh '''
                    docker run --rm \
                        -e OAUTH_CLIENT_ID="${OAUTH_CLIENT_ID}" \
                        -e OAUTH_CLIENT_SECRET="${OAUTH_CLIENT_SECRET}" \
                        -e OAUTH_TOKEN_ENDPOINT="${OAUTH_TOKEN_ENDPOINT}" \
                        -e API_ENDPOINT="${API_ENDPOINT}" \
                        nova-act-cicd-runner:latest \
                        --suite-id ${TEST_SUITE_ID} \
                        --var branch=${BRANCH_NAME} \
                        --verbose
                '''
            }
        }
    }
}
```

Jenkins will automatically create jobs for each branch and run tests on commits.

## Related Documentation

- [Configuration Reference](../configuration.md) - Environment variables and CLI arguments
- [CLI Reference](../cli-reference.md) - Detailed CLI usage
- [Troubleshooting Guide](../troubleshooting.md) - Common errors and solutions
- [Best Practices](../best-practices.md) - Security and optimization guidance
- [API Reference](../api-reference.md) - API documentation for advanced integration

## Support

For Jenkins integration assistance:

1. Check the [Jenkins documentation](https://www.jenkins.io/doc/)
2. Review [Troubleshooting Guide](../troubleshooting.md)
3. Enable verbose logging (`--verbose`) for detailed diagnostics
4. Check [GitHub Issues](https://github.com/aws-samples/sample-nova-act-qa-studio/issues)
5. Contact your platform administrator
