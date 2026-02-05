"""
WebSocket message handlers

Handles different types of WebSocket messages and commands.
"""

import logging
from typing import Dict, Any, Callable
from api.websocket.manager import get_websocket_manager

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming WebSocket messages"""
    
    def __init__(self):
        self.handlers: Dict[str, Callable] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default message handlers"""
        self.register("ping", self.handle_ping)
        self.register("subscribe", self.handle_subscribe)
        self.register("unsubscribe", self.handle_unsubscribe)
        self.register("broadcast", self.handle_broadcast)
    
    def register(self, message_type: str, handler: Callable):
        """Register a handler for a message type"""
        self.handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    async def handle_message(self, client_id: str, message: Dict[str, Any]):
        """Route message to appropriate handler"""
        message_type = message.get("type", "unknown")
        
        if message_type not in self.handlers:
            logger.warning(f"Unknown message type: {message_type}")
            return {
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            }
        
        try:
            return await self.handlers[message_type](client_id, message)
        except Exception as e:
            logger.error(f"Error handling message type {message_type}: {e}")
            return {
                "type": "error",
                "message": str(e)
            }
    
    async def handle_ping(self, client_id: str, message: Dict[str, Any]):
        """Handle ping message"""
        return {
            "type": "pong",
            "timestamp": message.get("timestamp"),
            "client_id": client_id
        }
    
    async def handle_subscribe(self, client_id: str, message: Dict[str, Any]):
        """Handle subscription request"""
        topic = message.get("topic")
        logger.info(f"Client {client_id} subscribing to {topic}")
        
        # TODO: Implement topic subscription logic
        
        return {
            "type": "subscribed",
            "topic": topic,
            "client_id": client_id
        }
    
    async def handle_unsubscribe(self, client_id: str, message: Dict[str, Any]):
        """Handle unsubscribe request"""
        topic = message.get("topic")
        logger.info(f"Client {client_id} unsubscribing from {topic}")
        
        # TODO: Implement topic unsubscription logic
        
        return {
            "type": "unsubscribed",
            "topic": topic,
            "client_id": client_id
        }
    
    async def handle_broadcast(self, client_id: str, message: Dict[str, Any]):
        """Handle broadcast request"""
        session_id = message.get("session_id", "default")
        content = message.get("content", {})
        
        ws_manager = get_websocket_manager()
        
        broadcast_message = {
            "type": "broadcast",
            "from": client_id,
            "content": content
        }
        
        await ws_manager.broadcast_to_session(session_id, broadcast_message)
        
        return {
            "type": "broadcast_sent",
            "session_id": session_id
        }


# Global message handler
_message_handler: Optional[MessageHandler] = None


def get_message_handler() -> MessageHandler:
    """Get the global message handler instance"""
    global _message_handler
    if _message_handler is None:
        _message_handler = MessageHandler()
    return _message_handler
