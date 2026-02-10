#!/usr/bin/env python3
"""
Deep integration layer for Dashboard into MCP Bus server
"""
import os
from pathlib import Path
from dash import Dash
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.staticfiles import StaticFiles

# Initialize Dash app instance
app = Dash(
    __name__, 
    suppress_callback_exceptions=True, 
    requests_pathname_prefix="/dashboard/",
    # Use MCP Bus assets
    assets_folder=str(Path(__file__).parent.parent.parent / "web_viewer"),
    # Disable built-in Flask debug server
    serve_locally=False
)

# Configure Dash app
app.title = "Quant Control Center"

# Build ID from environment or generate
BUILD_ID = os.getenv("BUILD_ID", "dev")

# Set a default placeholder layout to prevent JSON serialization errors during initialization
from dash import html, dcc

app.layout = html.Div([
    html.H1("Quant Control Center", style={"padding": "0 20px"}),
    html.P("Initializing Dashboard...", style={"padding": "0 20px"}),
    dcc.Interval(id="refresh", interval=10000, n_intervals=0, disabled=True),
    dcc.Store(id="ui-click-store", data={"last_button": None, "timestamp": 0}),
    dcc.Store(id="preflight-store", data={}),
    dcc.Store(id="preflight-trigger", data={}),
    dcc.Location(id="url", refresh=False),
])

# Import Dashboard components and callbacks
def init_dashboard_components():
    """Initialize Dashboard components and callbacks"""
    try:
        # Add the isolated_observatory/scripts/dashboard directory to Python path
        import sys
        from pathlib import Path
        dashboard_path = str(Path(__file__).parent.parent.parent.parent / "isolated_observatory" / "scripts" / "dashboard")
        if dashboard_path not in sys.path:
            sys.path.insert(0, dashboard_path)
        
        # Check if the components directory exists
        components_path = Path(dashboard_path) / "components"
        if not components_path.exists():
            print(f"Warning: Dashboard components directory not found at {components_path}")
            # Keep the default layout
            return True
        
        # Import Dashboard components
        try:
            from components.account_component import layout as account_layout
            from components.account_component import register_callbacks as register_account_callbacks
            from components.exceptions_component import layout as exceptions_layout
            from components.exceptions_component import register_callbacks as register_exceptions_callbacks
            from components.exchange_adapter_component import layout as exchange_adapter_layout
            from components.exchange_adapter_component import register_callbacks as register_exchange_adapter_callbacks
            from components.okx_connection_component import layout as okx_connection_layout
            from components.okx_connection_component import register_callbacks as register_okx_connection_callbacks
            from components.order_executor_component import layout as order_executor_layout
            from components.order_executor_component import register_callbacks as register_order_executor_callbacks
            from components.order_validator_component import layout as order_validator_layout
            from components.order_validator_component import register_callbacks as register_order_validator_callbacks
            from components.risk_gate_component import layout as risk_gate_layout
            from components.risk_gate_component import register_callbacks as register_risk_gate_callbacks
            from components.signal_bus_component import layout as signal_bus_layout
            from components.signal_bus_component import register_callbacks as register_signal_bus_callbacks
            from components.state_storage_component import layout as state_storage_layout
            from components.state_storage_component import register_callbacks as register_state_storage_callbacks
            from config_manager import layout as config_manager_layout
            from config_manager import register_callbacks as register_config_callbacks
            from navigation import create_navigation_bar
            from data_access import DataAccess
        except ImportError as e:
            print(f"Warning: Could not import some Dashboard components: {e}")
            # Keep the default layout
            return True
        
        # Import additional modules needed for layout
        from data_access import DataAccess
        from navigation import create_navigation_bar
        
        # Initialize shared services
        data_access = DataAccess()
        
        # Register callbacks
        try:
            register_config_callbacks(app)
            register_account_callbacks(app, data_access)
            register_risk_gate_callbacks(app, data_access)
            register_signal_bus_callbacks(app, data_access)
            register_order_executor_callbacks(app, data_access)
            register_state_storage_callbacks(app, data_access)
            register_exceptions_callbacks(app, data_access)
            register_exchange_adapter_callbacks(app, data_access)
            register_order_validator_callbacks(app, data_access)
            register_okx_connection_callbacks(app, data_access)
        except Exception as e:
            print(f"Warning: Could not register some Dashboard callbacks: {e}")
        
        # Set up basic layout for Dash app
        app.layout = html.Div([
            # Navigation bar
            create_navigation_bar(),
            
            # Basic page structure
            html.Div([
                html.H1("Quant Control Center", style={"padding": "0 20px"}),
                html.P("Dashboard is running in deep integration mode", style={"padding": "0 20px"}),
                html.H2("BUILD_ID: " + BUILD_ID, style={"padding": "0 20px"}),
                
                # Main content area
                html.Div([
                    html.H3("Dashboard Components", style={"marginBottom": "15px"}),
                    html.Div([
                        html.H4("Account Component"),
                        account_layout
                    ], style={"marginBottom": "20px"}),
                    
                    html.Div([
                        html.H4("Config Manager"),
                        config_manager_layout
                    ], style={"marginBottom": "20px"}),
                ], style={"padding": "0 20px"}),
            ]),
            
            # Hidden components required for callbacks
            dcc.Interval(id="refresh", interval=10000, n_intervals=0, disabled=False),
            dcc.Store(id="ui-click-store", data={"last_button": None, "timestamp": 0}),
            dcc.Store(id="preflight-store", data={}),
            dcc.Store(id="preflight-trigger", data={}),
            dcc.Location(id="url", refresh=False),
        ])
        
        return True
    except Exception as e:
        print(f"Error initializing Dashboard components: {e}")
        import traceback
        traceback.print_exc()
        return False

# FastAPI integration function
def configure_dash_integration(fastapi_app):
    """Configure Dash integration with FastAPI"""
    # Initialize Dashboard components
    success = init_dashboard_components()
    if not success:
        print("Warning: Dashboard components initialization failed")
        return None
    
    # Mount Dash as WSGI app
    fastapi_app.mount("/dashboard", WSGIMiddleware(app.server))
    
    # Serve Dash static files through FastAPI for better performance
    web_viewer_dir = str(Path(__file__).parent.parent.parent / "web_viewer")
    if Path(web_viewer_dir).exists():
        fastapi_app.mount(
            "/web_viewer",
            StaticFiles(directory=web_viewer_dir),
            name="web_viewer"
        )
    
    # Configure Dash static files
    fastapi_app.mount(
        "/_dash-component-suites",
        StaticFiles(directory=str(Path(__file__).parent.parent / "static" / "_dash-component-suites")),
        name="dash-component-suites"
    )
    
    # Add Dashboard static folder for assets
    fastapi_app.mount(
        "/assets",
        StaticFiles(directory=str(Path(__file__).parent.parent.parent / "web_viewer")),
        name="dash-assets"
    )
    
    print("✅ Dashboard integration configured successfully")
    return app

# Shared services bridge
def get_shared_services():
    """Get shared services for Dashboard"""
    from .freqtrade_service import freqtrade_service
    from .monitoring import monitoring_service
    from .chart_service import chart_service
    
    return {
        "freqtrade_service": freqtrade_service,
        "monitoring_service": monitoring_service,
        "chart_service": chart_service
    }
