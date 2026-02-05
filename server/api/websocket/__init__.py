"""
WebSocket module for real-time communication

Provides WebSocket manager for live telemetry streaming and updates.
"""

from api.websocket.manager import WebSocketManager, ConnectionManager

__all__ = [
    "WebSocketManager",
    "ConnectionManager",
]
