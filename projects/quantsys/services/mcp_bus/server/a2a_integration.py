#!/usr/bin/env python3
"""
Deep integration layer for A2A Hub into MCP Bus server
"""
import os
import sys
from pathlib import Path
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.staticfiles import StaticFiles

# Add the a2a_hub directory to Python path
a2a_hub_path = str(Path(__file__).parent.parent.parent / "a2a_hub")
if a2a_hub_path not in sys.path:
    sys.path.insert(0, a2a_hub_path)

def configure_a2a_integration(fastapi_app):
    """Configure A2A Hub integration with FastAPI"""
    try:
        # Import A2A Hub Flask app
        from main import app as a2a_app
        
        # Set up A2A Hub configuration
        a2a_app.config["SECRET_KEY"] = os.getenv("A2A_HUB_SECRET_KEY")
        
        # Mount A2A Hub as WSGI app
        fastapi_app.mount("/a2a", WSGIMiddleware(a2a_app))
        
        # Mount A2A Hub static files if any
        a2a_static_path = Path(a2a_hub_path) / "static"
        if a2a_static_path.exists():
            fastapi_app.mount(
                "/a2a/static",
                StaticFiles(directory=str(a2a_static_path)),
                name="a2a-static"
            )
        
        print("OK A2A Hub integration configured successfully")
        return a2a_app
    except Exception as e:
        print(f"Error initializing A2A Hub integration: {e}")
        import traceback
        traceback.print_exc()
        return None
