#!/usr/bin/env python3
"""
Demo script showing cache_parser in action with real-world scenarios.
"""

import sys
sys.path.insert(0, '/Users/jawie/Repositories/programs/sample-nova-act-qa-studio/web-app/worker')

from cache_parser import parse_nova_act_steps
import json

print("=" * 70)
print("Cache Parser Demo - Real-World Scenarios")
print("=" * 70)

# Scenario 1: Close popup
print("\n📋 Scenario 1: Close popup")
response1 = {
    'steps': [
        {
            'response': {
                'rawProgramBody': 'think("Looking for popup close button");\nagentClick("<box>621,71,640,143</box>");'
            }
        },
        {
            'response': {
                'rawProgramBody': 'think("Popup closed successfully");\nreturn();'
            }
        }
    ]
}
result1 = parse_nova_act_steps(response1)
print(f"Input: 2 steps (think + click + think + return)")
print(f"Output: {json.dumps(result1, indent=2)}")

# Scenario 2: Login flow
print("\n📋 Scenario 2: Login with username and password")
response2 = {
    'steps': [
        {
            'response': {
                'rawProgramBody': 'agentType("admin", "<box>300,400,500,450</box>");'
            }
        },
        {
            'response': {
                'rawProgramBody': 'agentType("password123", "<box>300,500,500,550</box>", true);'
            }
        }
    ]
}
result2 = parse_nova_act_steps(response2)
print(f"Input: 2 type actions (username + password with Enter)")
print(f"Output: {json.dumps(result2, indent=2)}")

# Scenario 3: Navigation and scroll
print("\n📋 Scenario 3: Navigate and scroll")
response3 = {
    'steps': [
        {
            'response': {
                'rawProgramBody': 'goToUrl("https://example.com/products");'
            }
        },
        {
            'response': {
                'rawProgramBody': 'agentScroll("down", "<box>0,0,1920,1080</box>", 500.0);'
            }
        }
    ]
}
result3 = parse_nova_act_steps(response3)
print(f"Input: Navigate + scroll down")
print(f"Output: {json.dumps(result3, indent=2)}")

# Scenario 4: No cacheable actions
print("\n📋 Scenario 4: No cacheable actions (only think/return)")
response4 = {
    'steps': [
        {
            'response': {
                'rawProgramBody': 'think("Analyzing page structure");'
            }
        },
        {
            'response': {
                'rawProgramBody': 'return();'
            }
        }
    ]
}
result4 = parse_nova_act_steps(response4)
print(f"Input: Only think() and return()")
print(f"Output: {result4} (None - no cacheable actions)")

print("\n" + "=" * 70)
print("✅ All scenarios processed successfully!")
print("=" * 70)
