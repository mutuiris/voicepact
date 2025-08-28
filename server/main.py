import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import init_database, close_database, health_check
from app.api.v1.api import api_router
from app.services.africastalking_client import close_africastalking_client
from app.services.voice_processor import close_voice_processor

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format,
    filename=settings.log_file if settings.log_file else None
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    
    try:
        await init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    await close_database()
    await close_africastalking_client()
    await close_voice_processor()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    **settings.fastapi_kwargs,
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API router
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception in {request.method} {request.url}: {exc}")
    
    if settings.debug:
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.debug else "An error occurred"
        }
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "healthy"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    health_status = await health_check()
    
    overall_status = "healthy" if all(
        "error" not in status for status in health_status.values()
    ) else "unhealthy"
    
    return {
        "status": overall_status,
        "services": health_status,
        "timestamp": asyncio.get_event_loop().time()
    }


@app.get("/info")
async def info():
    """Application information"""
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "debug": settings.debug,
        "features": {
            "voice_processing": True,
            "sms_integration": True,
            "payment_escrow": True,
            "ussd_support": True,
            "contract_generation": True,
            "crypto_signatures": True
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        access_log=True
    )