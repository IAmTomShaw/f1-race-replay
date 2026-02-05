"""
WebSocket Connection Manager

Handles WebSocket connections, broadcasting, and client management.
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set, Optional, Any
import json
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for a single session"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.active_connections: List[WebSocket] = []
        self.client_info: Dict[WebSocket, Dict[str, Any]] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.client_info[websocket] = {
            "client_id": client_id,
            "connected_at": datetime.now().isoformat(),
            "session_id": self.session_id
        }
        logger.info(f"Client {client_id} connected to session {self.session_id}")
        
        # Send welcome message
        await self.send_personal_message({
            "type": "connection",
            "status": "connected",
            "session_id": self.session_id,
            "client_id": client_id,
            "message": "Successfully connected to WebSocket"
        }, websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            client_id = self.client_info.get(websocket, {}).get("client_id", "unknown")
            self.active_connections.remove(websocket)
            if websocket in self.client_info:
                del self.client_info[websocket]
            logger.info(f"Client {client_id} disconnected from session {self.session_id}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast(self, message: dict, exclude: Optional[WebSocket] = None):
        """Broadcast a message to all connected clients"""
        disconnected = []
        
        for connection in self.active_connections:
            if connection == exclude:
                continue
            
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_text(self, text: str, exclude: Optional[WebSocket] = None):
        """Broadcast a text message to all connected clients"""
        disconnected = []
        
        for connection in self.active_connections:
            if connection == exclude:
                continue
            
            try:
                await connection.send_text(text)
            except Exception as e:
                logger.error(f"Error broadcasting text: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)
    
    def get_client_info(self) -> List[Dict[str, Any]]:
        """Get information about all connected clients"""
        return list(self.client_info.values())


class WebSocketManager:
    """Global WebSocket manager for all sessions"""
    
    def __init__(self):
        # Map of session_id -> ConnectionManager
        self.sessions: Dict[str, ConnectionManager] = {}
        
        # Map of client_id -> (session_id, websocket)
        self.clients: Dict[str, tuple[str, WebSocket]] = {}
        
        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 30  # seconds
    
    def get_or_create_session(self, session_id: str) -> ConnectionManager:
        """Get or create a ConnectionManager for a session"""
        if session_id not in self.sessions:
            self.sessions[session_id] = ConnectionManager(session_id)
            logger.info(f"Created new session manager: {session_id}")
        return self.sessions[session_id]
    
    async def connect(self, client_id: str, websocket: WebSocket, session_id: str = "default"):
        """Connect a client to a session"""
        # Get or create session manager
        session_manager = self.get_or_create_session(session_id)
        
        # Connect to session
        await session_manager.connect(websocket, client_id)
        
        # Track client globally
        self.clients[client_id] = (session_id, websocket)
        
        # Start heartbeat if not running
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    def disconnect(self, client_id: str):
        """Disconnect a client"""
        if client_id in self.clients:
            session_id, websocket = self.clients[client_id]
            
            # Disconnect from session
            if session_id in self.sessions:
                self.sessions[session_id].disconnect(websocket)
                
                # Remove empty sessions
                if self.sessions[session_id].get_connection_count() == 0:
                    del self.sessions[session_id]
                    logger.info(f"Removed empty session: {session_id}")
            
            # Remove from global tracking
            del self.clients[client_id]
    
    async def send_to_client(self, client_id: str, message: dict):
        """Send a message to a specific client"""
        if client_id in self.clients:
            session_id, websocket = self.clients[client_id]
            if session_id in self.sessions:
                await self.sessions[session_id].send_personal_message(message, websocket)
    
    async def broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast a message to all clients in a session"""
        if session_id in self.sessions:
            await self.sessions[session_id].broadcast(message)
    
    async def broadcast_to_all(self, message: dict):
        """Broadcast a message to all clients in all sessions"""
        for session_manager in self.sessions.values():
            await session_manager.broadcast(message)
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            return {
                "session_id": session_id,
                "connection_count": session.get_connection_count(),
                "clients": session.get_client_info()
            }
        return None
    
    def get_all_sessions_info(self) -> List[Dict[str, Any]]:
        """Get information about all sessions"""
        return [
            self.get_session_info(session_id)
            for session_id in self.sessions.keys()
        ]
    
    def get_total_connections(self) -> int:
        """Get total number of active connections across all sessions"""
        return sum(
            session.get_connection_count()
            for session in self.sessions.values()
        )
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to all clients"""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                if self.get_total_connections() == 0:
                    # No clients, stop heartbeat
                    logger.info("No active connections, stopping heartbeat")
                    break
                
                heartbeat_message = {
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat(),
                    "total_connections": self.get_total_connections()
                }
                
                await self.broadcast_to_all(heartbeat_message)
                logger.debug(f"Sent heartbeat to {self.get_total_connections()} clients")
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")


# Global WebSocket manager instance
_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
