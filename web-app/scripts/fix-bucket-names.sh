#!/bin/bash

# Fix cross-region S3 bucket names to include account ID prefix
# Old format: nova-act-qa-studio-modular-artefacts-{region}
# New format: 672106413069-nova-act-qa-studio-modular-artefacts-{region}

set -e

ACCOUNT_ID="672106413069"
BASE_NAME="nova-act-qa-studio-modular"
REGIONS=("us-east-1" "us-west-2" "ap-southeast-2")

echo "Fixing cross-region bucket names..."
echo "Account ID: $ACCOUNT_ID"
echo "Base Name: $BASE_NAME"
echo ""

for REGION in "${REGIONS[@]}"; do
    OLD_BUCKET="${BASE_NAME}-artefacts-${REGION}"
    NEW_BUCKET="${ACCOUNT_ID}-${BASE_NAME}-artefacts-${REGION}"
    
    echo "Processing region: $REGION"
    echo "  Old bucket: $OLD_BUCKET"
    echo "  New bucket: $NEW_BUCKET"
    
    # Check if old bucket exists
    if aws s3 ls "s3://$OLD_BUCKET" --region "$REGION" 2>/dev/null; then
        echo "  ✓ Old bucket exists"
        
        # Check if new bucket already exists
        if aws s3 ls "s3://$NEW_BUCKET" --region "$REGION" 2>/dev/null; then
            echo "  ⚠ New bucket already exists, skipping..."
        else
            echo "  → Creating new bucket..."
            if [ "$REGION" == "us-east-1" ]; then
                aws s3 mb "s3://$NEW_BUCKET" --region "$REGION"
            else
                aws s3 mb "s3://$NEW_BUCKET" --region "$REGION" --create-bucket-configuration LocationConstraint="$REGION"
            fi
            
            echo "  → Enabling versioning..."
            aws s3api put-bucket-versioning \
                --bucket "$NEW_BUCKET" \
                --versioning-configuration Status=Enabled \
                --region "$REGION"
            
            echo "  → Copying objects from old to new bucket..."
            aws s3 sync "s3://$OLD_BUCKET" "s3://$NEW_BUCKET" --region "$REGION"
            
            echo "  → Emptying old bucket..."
            aws s3 rm "s3://$OLD_BUCKET" --recursive --region "$REGION"
            
            echo "  → Deleting old bucket..."
            aws s3 rb "s3://$OLD_BUCKET" --region "$REGION"
            
            echo "  ✓ Migration complete for $REGION"
        fi
    else
        echo "  ℹ Old bucket doesn't exist, checking if new bucket exists..."
        if aws s3 ls "s3://$NEW_BUCKET" --region "$REGION" 2>/dev/null; then
            echo "  ✓ New bucket already exists"
        else
            echo "  ✗ Neither bucket exists, will be created by CDK"
        fi
    fi
    echo ""
done

echo "Bucket name fix complete!"
echo ""
echo "Next steps:"
echo "1. Update worker Lambda environment variables to use new bucket names"
echo "2. Redeploy worker stack: npm run deploy:worker"
