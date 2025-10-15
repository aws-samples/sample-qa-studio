#!/bin/bash

# Deployment script for NovaAct QA Studio
# Ensures proper deployment order to avoid circular dependencies

set -e  # Exit on error

# Get base name from configuration.json
BASE_NAME=$(jq -r '.baseName' configuration.json)
LAMBDA_FOLDER="lambda/cmd"

if [ -z "$BASE_NAME" ] || [ "$BASE_NAME" = "null" ]; then
  echo "❌ Error: Could not read baseName from configuration.json"
  exit 1
fi

# Use AWS_REGION or AWS_DEFAULT_REGION, fallback to us-east-1
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

echo "🚀 Starting deployment for: $BASE_NAME"
echo "🌍 Region: $REGION"
echo ""

echo "🔨  Build Lambdas..."
for f in $(find ${LAMBDA_FOLDER} -type d -maxdepth 1 -mindepth 1 -exec basename {} \;); do sh -c "cd ${LAMBDA_FOLDER}/$f && GOOS=linux GOARCH=arm64 go build -tags lambda.norpc -o bootstrap main.go && echo \"[\033[0;32m OK \033[0m] $f\"" _ "${f}"; done


echo "☁️  Deploying storage stack..."
npx cdk deploy storage --require-approval never

echo "☁️  Deploying auth stack..."
npx cdk deploy auth --require-approval never

echo "☁️  Deploying api stack..."
npx cdk deploy api --require-approval never

echo "☁️  Deploying frontend stack..."
npx cdk deploy frontend --require-approval never

echo "☁️  Generating frontend configuration from stack outputs..."
npx ts-node scripts/write-config.ts "$BASE_NAME"

echo "🔨  Building frontend..."
cd frontend && npm run build && cd ..

echo "☁️  Deploying frontend..."
npx cdk deploy frontend_deployment --require-approval never

echo "☁️  Re-synthesizing to pick up SSM parameter..."
npx cdk synth > /dev/null

echo "☁️  Deploying notification stack..."
npx cdk deploy notification --require-approval never

echo "☁️  Deploying worker stack..."
npx cdk deploy worker --require-approval never

echo "☁️  Deploying routes stack..."
npx cdk deploy routes --require-approval never

echo "🔨  Removing Lambdas..."
find ${LAMBDA_FOLDER} -name "bootstrap" -type f -delete 2>/dev/null || true

echo ""
echo "✅ Deployment complete!"
echo "📝 Frontend config written to: frontend/src/amplifyconfiguration.json"
