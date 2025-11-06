"""Main FastAPI application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import chat, scrape
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="PartSelect Chat Agent",
    description="A chat agent backend for PartSelect e-commerce website specializing in Refrigerator and Dishwasher parts",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router)
app.include_router(scrape.router)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("PartSelect Chat Agent starting up...")
    logger.info("Services initialized successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("PartSelect Chat Agent shutting down...")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "PartSelect Chat Agent API",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/api/chat",
            "scrape": "/api/scrape",
            "health": "/api/health",
            "sessions": {
                "create": "/api/sessions/new",
                "get_history": "/api/sessions/{session_id}/history",
                "delete": "/api/sessions/{session_id}",
                "clear": "/api/sessions/{session_id}/clear"
            }
        }
    }

