"""
Lambda initialization helper.
Adds the dependencies folder to Python path if it exists.
Import this at the top of Lambda handlers so dependencies are available.
"""
import sys
import os

# Add dependencies folder to Python path
dependencies_path = os.path.join(os.path.dirname(__file__), 'dependencies')
if os.path.exists(dependencies_path) and dependencies_path not in sys.path:
    sys.path.insert(0, dependencies_path)
