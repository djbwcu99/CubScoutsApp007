# Vercel serverless entry point — wraps the Flask app in server.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from server import app  # noqa: E402,F401
