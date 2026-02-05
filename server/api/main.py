from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import logging

from ..config.settings import get_settings
from api.routes import races, telemetry, sessions

from fastapi import WebSocket, WebSocketDisconnect
from api.websocket.manager import get_websocket_manager
from api.websocket.handlers import get_message_handler
import json

# Get settings
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format=settings.log_format,
    filename=settings.log_file
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Mount static files
static_path = settings.get_static_path()
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Include routers
app.include_router(races.router, prefix=f"{settings.api_prefix}/races", tags=["races"])
app.include_router(telemetry.router, prefix=f"{settings.api_prefix}/telemetry", tags=["telemetry"])

@app.get("/")
async def root():
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "debug": settings.debug,
        "version": settings.app_version
    }

@app.get("/config")
async def config():
    """Get public configuration (non-sensitive)"""
    return {
        "min_year": settings.min_year,
        "max_year": settings.max_year,
        "enable_qualifying": settings.enable_qualifying,
        "enable_weather": settings.enable_weather,
    }

if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Allowed years: {settings.min_year}-{settings.max_year}")
    
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )

ws_manager = get_websocket_manager()
message_handler = get_message_handler()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, session_id: str = "default"):
    """
    WebSocket endpoint for real-time communication
    
    Args:
        client_id: Unique client identifier
        session_id: Session/room identifier (optional, default: "default")
    """
    await ws_manager.connect(client_id, websocket, session_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Handle message
                response = await message_handler.handle_message(client_id, message)
                
                # Send response back to client
                if response:
                    await ws_manager.send_to_client(client_id, response)
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from client {client_id}: {data}")
                await ws_manager.send_to_client(client_id, {
                    "type": "error",
                    "message": "Invalid JSON format"
                })
            
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
        ws_manager.disconnect(client_id)


@app.get("/ws/sessions")
async def get_websocket_sessions():
    """Get information about all active WebSocket sessions"""
    return {
        "sessions": ws_manager.get_all_sessions_info(),
        "total_connections": ws_manager.get_total_connections()
    }


@app.get("/ws/session/{session_id}")
async def get_websocket_session_info(session_id: str):
    """Get information about a specific WebSocket session"""
    info = ws_manager.get_session_info(session_id)
    
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return info