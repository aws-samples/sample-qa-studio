#!/usr/bin/env python3
"""
Test script for OAuth M2M authentication.

Usage:
    python test_oauth_client.py --client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> \
                                 --cognito-domain <DOMAIN> --api-url <API_URL> \
                                 --endpoint <ENDPOINT> [--method GET|POST] [--json <JSON_DATA>]

Example:
    # GET request
    python test_oauth_client.py \
        --client-id 1a2b3c4d5e6f7g8h9i0j \
        --client-secret abcdef123456 \
        --cognito-domain https://my-domain.auth.us-east-1.amazoncognito.com \
        --api-url https://abc123.execute-api.us-east-1.amazonaws.com/prod \
        --endpoint /usecases \
        --method GET

    # POST request with JSON
    python test_oauth_client.py \
        --client-id 1a2b3c4d5e6f7g8h9i0j \
        --client-secret abcdef123456 \
        --cognito-domain https://my-domain.auth.us-east-1.amazoncognito.com \
        --api-url https://abc123.execute-api.us-east-1.amazonaws.com/prod \
        --endpoint /usecase/123/execute \
        --method POST \
        --json '{"key": "value"}'
"""

import argparse
import base64
import json
import sys
import time
from typing import Optional, Dict, Any
import requests


class OAuthClient:
    """OAuth M2M client for testing API access."""
    
    def __init__(self, client_id: str, client_secret: str, cognito_domain: str, api_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.cognito_domain = cognito_domain.rstrip('/')
        self.api_url = api_url.rstrip('/')
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[float] = None
    
    def get_access_token(self) -> str:
        """Get an access token using client credentials flow."""
        # Check if we have a valid cached token
        if self.access_token and self.token_expiry and time.time() < self.token_expiry:
            print("✓ Using cached access token")
            return self.access_token
        
        print("→ Requesting new access token...")
        
        # Encode credentials for Basic Auth
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        # Request token
        response = requests.post(
            f"{self.cognito_domain}/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}"
            },
            data={
                "grant_type": "client_credentials",
                "scope": "api/execute"
            }
        )
        
        if response.status_code != 200:
            print(f"✗ Failed to get access token: {response.status_code}")
            print(f"  Response: {response.text}")
            sys.exit(1)
        
        token_data = response.json()
        self.access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self.token_expiry = time.time() + expires_in - 60  # Refresh 1 min before expiry
        
        print(f"✓ Got access token (expires in {expires_in}s)")
        
        # Decode and display token info (for debugging)
        try:
            import json as json_lib
            # JWT tokens have 3 parts: header.payload.signature
            parts = self.access_token.split('.')
            if len(parts) >= 2:
                # Decode payload (add padding if needed)
                payload = parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.b64decode(payload)
                token_info = json_lib.loads(decoded)
                print(f"  Token info:")
                print(f"    - Client ID: {token_info.get('client_id', 'N/A')}")
                print(f"    - Scope: {token_info.get('scope', 'N/A')}")
                print(f"    - Token use: {token_info.get('token_use', 'N/A')}")
                if 'aud' in token_info:
                    print(f"    - Audience: {token_info.get('aud', 'N/A')}")
                print(f"\n  Full token payload:")
                print(f"  {json_lib.dumps(token_info, indent=4)}")
                print(f"\n  Full access token:")
                print(f"  {self.access_token}")
        except Exception as e:
            print(f"  (Could not decode token info: {e})")
        
        return self.access_token
    
    def api_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> requests.Response:
        """Make an authenticated API request."""
        token = self.get_access_token()
        
        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }
        
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        print(f"\n{'='*60}")
        print(f"Making API Request")
        print(f"{'='*60}")
        print(f"Method:   {method}")
        print(f"Endpoint: {endpoint}")
        print(f"URL:      {url}")
        if json_data:
            print(f"Body:     {json.dumps(json_data, indent=2)}")
        
        try:
            if json_data:
                response = requests.request(method, url, headers=headers, json=json_data)
            else:
                response = requests.request(method, url, headers=headers)
            
            print(f"\n{'='*60}")
            print(f"Response")
            print(f"{'='*60}")
            print(f"Status Code: {response.status_code}")
            print(f"Headers:")
            for key, value in response.headers.items():
                print(f"  {key}: {value}")
            
            print(f"\nBody:")
            try:
                response_json = response.json()
                print(json.dumps(response_json, indent=2))
            except:
                print(response.text if response.text else "(empty)")
            
            return response
            
        except requests.exceptions.ConnectionError as e:
            print(f"\n✗ Connection Error: Unable to reach {self.api_url}")
            print(f"  Error: {str(e)}")
            print(f"\n  Troubleshooting:")
            print(f"  1. Verify the API URL is correct")
            print(f"  2. Check if the API Gateway/CloudFront is deployed")
            print(f"  3. Ensure you have network connectivity")
            print(f"  4. Try accessing the URL in a browser")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Test OAuth M2M authentication with the API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--client-id', required=True, help='OAuth Client ID')
    parser.add_argument('--client-secret', required=True, help='OAuth Client Secret')
    parser.add_argument('--cognito-domain', required=True, help='Cognito domain URL')
    parser.add_argument('--api-url', required=True, help='API Gateway URL')
    parser.add_argument('--endpoint', required=True, help='API endpoint to test (e.g., /usecases)')
    parser.add_argument('--method', default='GET', choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'], 
                       help='HTTP method (default: GET)')
    parser.add_argument('--json', type=str, help='JSON data for POST/PUT requests (as string)')
    
    args = parser.parse_args()
    
    # Parse JSON data if provided
    json_data = None
    if args.json:
        try:
            json_data = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON: {e}")
            sys.exit(1)
    
    print("=" * 60)
    print("OAuth M2M API Test")
    print("=" * 60)
    
    # Create client
    client = OAuthClient(
        client_id=args.client_id,
        client_secret=args.client_secret,
        cognito_domain=args.cognito_domain,
        api_url=args.api_url
    )
    
    # Make the API request
    response = client.api_request(args.method, args.endpoint, json_data)
    
    print(f"\n{'='*60}")
    print("Test Complete")
    print(f"{'='*60}")
    
    # Exit with appropriate code
    if 200 <= response.status_code < 300:
        print("✓ Request successful")
        sys.exit(0)
    else:
        print(f"✗ Request failed with status {response.status_code}")
        sys.exit(1)


if __name__ == '__main__':
    main()
