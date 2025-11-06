"""Chat API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from app.agent.tool_agent import ToolAgent
from app.session_manager import session_manager
from app.feedback_analyzer import feedback_analyzer
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# Lazy initialization - agent created on first use
_tool_agent = None

def get_agent():
    """Get the tool-based agent (lazy initialization)."""
    global _tool_agent
    
    if _tool_agent is None:
        _tool_agent = ToolAgent()
    return _tool_agent


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str  # 'user' or 'assistant'
    content: str


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    session_id: Optional[str] = None  # If not provided, a new session will be created


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    session_id: str
    intent: Optional[str] = None
    entities: Optional[Dict] = None
    sources_used: Optional[int] = None
    source_urls: Optional[List[str]] = []


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat requests with per-session conversation history."""
    try:
        # Get or create session
        if request.session_id:
            session_id = request.session_id
            logger.info(f"🔄 Using existing session: {session_id}")
            # Get recent history from in-memory cache (last 5 messages for LLM context)
            history = session_manager.get_recent_history(session_id)
            logger.info(f"   Retrieved {len(history)} cached messages for LLM context")
        else:
            # Create new session
            logger.info("🆕 No session_id provided, creating new session")
            session_id = session_manager.create_session()
            history = []
        
        # Log incoming user message
        user_msg_preview = request.message[:100] + "..." if len(request.message) > 100 else request.message
        logger.info(f"📨 Processing user message for session {session_id}: {user_msg_preview}")
        
        # Analyze feedback for this session to improve prompts
        feedback_insights = feedback_analyzer.analyze_session_feedback(session_id)
        if feedback_insights.get('has_insights'):
            logger.info(f"📊 Feedback analysis: {feedback_insights['thumbs_up']} up, {feedback_insights['thumbs_down']} down (ratio: {feedback_insights['feedback_ratio']:.2%})")
            if feedback_insights.get('enhancements'):
                logger.info(f"   Applying {len(feedback_insights['enhancements'])} feedback-based improvements")
        
        # Process query with conversation history (before adding current message)
        # Uses in-memory cache (last 5 messages) for faster LLM context
        # Pass feedback insights to agent for prompt enhancement
        agent = get_agent()
        result = await agent.process_query(request.message, history, feedback_insights=feedback_insights)
        
        # Add user message to history (after processing)
        session_manager.add_message(session_id, 'user', request.message)
        
        # Get assistant response
        assistant_response = result.get('response', '')
        
        # Add assistant response to history
        session_manager.add_message(session_id, 'assistant', assistant_response)
        
        # Log summary
        final_history = session_manager.get_history(session_id)
        logger.info(f"✅ Chat completed for session {session_id} - Total messages: {len(final_history)}")
        
        return ChatResponse(
            response=assistant_response,
            session_id=session_id,
            intent=result.get('intent'),
            entities=result.get('entities'),
            sources_used=result.get('sources_used', 0),
            source_urls=result.get('source_urls', [])
        )
        
    except Exception as e:
        logger.error(f"❌ Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "PartSelect Chat Agent"
    }


@router.post("/sessions/new")
async def create_session():
    """Create a new chat session."""
    session_id = session_manager.create_session()
    return {
        "session_id": session_id,
        "message": "New session created"
    }


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """Get conversation history for a session."""
    history = session_manager.get_history(session_id)
    return {
        "session_id": session_id,
        "history": history,
        "message_count": len(history)
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its conversation history."""
    session_manager.delete_session(session_id)
    return {
        "session_id": session_id,
        "message": "Session deleted"
    }


@router.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """Clear conversation history for a session (keeps session alive)."""
    session_manager.clear_session(session_id)
    return {
        "session_id": session_id,
        "message": "Session history cleared"
    }


@router.get("/sessions")
async def list_sessions(limit: int = 100):
    """List all sessions ordered by most recent update."""
    sessions = session_manager.list_sessions(limit=limit)
    return {
        "sessions": sessions,
        "count": len(sessions)
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


class FeedbackRequest(BaseModel):
    """Feedback request model."""
    session_id: str
    message_content: str
    rating: str  # 'thumbs_up' or 'thumbs_down'


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Submit feedback for a message."""
    if request.rating not in ['thumbs_up', 'thumbs_down']:
        raise HTTPException(
            status_code=400, 
            detail="Rating must be 'thumbs_up' or 'thumbs_down'"
        )
    
    success = session_manager.add_feedback(
        session_id=request.session_id,
        message_content=request.message_content,
        rating=request.rating
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save feedback")
    
    return {
        "message": "Feedback recorded successfully",
        "session_id": request.session_id,
        "rating": request.rating
    }


@router.get("/feedback/stats")
async def get_feedback_stats(session_id: Optional[str] = None):
    """Get feedback statistics. Optionally filter by session_id."""
    stats = session_manager.get_feedback_stats(session_id)
    return stats

