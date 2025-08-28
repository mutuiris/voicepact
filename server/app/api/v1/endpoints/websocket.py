import json
import logging
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket client connected: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket client disconnected: {client_id}")

    async def send_personal_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)


manager = ConnectionManager()


@router.websocket("/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type", "unknown")
                
                if message_type == "ping":
                    await manager.send_personal_message(
                        json.dumps({"type": "pong", "timestamp": message.get("timestamp")}),
                        client_id
                    )
                
                elif message_type == "contract_status":
                    # Fetch contract status from DB; done as a placeholder
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "contract_status_response",
                            "contract_id": message.get("contract_id"),
                            "status": "active"
                        }),
                        client_id
                    )
                
                else:
                    logger.info(f"Unknown message type: {message_type} from {client_id}")
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from {client_id}: {data}")
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")


async def notify_contract_update(contract_id: str, status: str, parties: List[str]):
    """Notify connected clients about contract updates"""
    message = json.dumps({
        "type": "contract_update",
        "contract_id": contract_id,
        "status": status,
        "timestamp": str(int(datetime.utcnow().timestamp()))
    })
    
    # Send to specific parties if connected
    for phone_number in parties:
        await manager.send_personal_message(message, phone_number)


async def notify_payment_update(contract_id: str, payment_status: str, amount: float):
    """Notify connected clients about payment updates"""
    message = json.dumps({
        "type": "payment_update",
        "contract_id": contract_id,
        "status": payment_status,
        "amount": amount,
        "timestamp": str(int(datetime.utcnow().timestamp()))
    })
    
    await manager.broadcast(message)