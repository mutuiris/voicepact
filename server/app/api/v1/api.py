from fastapi import APIRouter

from app.api.v1.endpoints import contracts, payments, sms, ussd, voice, websocket

api_router = APIRouter()

# Individual endpoint routers
api_router.include_router(
    voice.router,
    prefix="/voice",
    tags=["voice"]
)

api_router.include_router(
    sms.router,
    prefix="/sms",
    tags=["sms"]
)

api_router.include_router(
    ussd.router,
    prefix="/ussd", 
    tags=["ussd"]
)

api_router.include_router(
    contracts.router,
    prefix="/contracts",
    tags=["contracts"]
)

api_router.include_router(
    payments.router,
    prefix="/payments",
    tags=["payments"]
)

api_router.include_router(
    websocket.router,
    prefix="/ws",
    tags=["websocket"]
)