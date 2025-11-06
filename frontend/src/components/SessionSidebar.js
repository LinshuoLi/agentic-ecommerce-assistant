import React, { useState, useEffect, useRef } from "react";
import "./SessionSidebar.css";
import { listSessions, createSession, deleteSession } from "../api/api";

function SessionSidebar({ currentSessionId, onSessionSelect, onNewSession, refreshTrigger }) {
  const [sessions, setSessions] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const isLoadingRef = useRef(false); // Track if a load is in progress

  const loadSessions = async () => {
    // Prevent concurrent loads
    if (isLoadingRef.current) {
      return;
    }
    
    isLoadingRef.current = true;
    setIsLoading(true);
    try {
      const sessionList = await listSessions();
      setSessions(sessionList);
    } catch (error) {
      console.error("Error loading sessions:", error);
    } finally {
      setIsLoading(false);
      isLoadingRef.current = false;
    }
  };

  useEffect(() => {
    loadSessions();
    // Only refresh when currentSessionId changes (user switches sessions or creates new one)
    // or when refreshTrigger changes (after messages are sent to update titles)
    // Removed automatic polling to reduce API calls
  }, [currentSessionId, refreshTrigger]);

  const handleNewSession = async () => {
    const newSessionId = await createSession();
    if (newSessionId) {
      // Don't call loadSessions here - let useEffect handle it when currentSessionId changes
      onNewSession(newSessionId);
    }
  };

  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation(); // Prevent selecting the session when clicking delete
    if (window.confirm("Are you sure you want to delete this conversation?")) {
      const success = await deleteSession(sessionId);
      if (success) {
        // Refresh sessions list after deletion
        await loadSessions();
        if (sessionId === currentSessionId) {
          // If we deleted the current session, create a new one
          handleNewSession();
        }
      }
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="session-sidebar">
      <div className="session-sidebar-header">
        <button className="new-chat-button" onClick={handleNewSession}>
          <span>+</span> New conversation
        </button>
      </div>
      
      <div className="session-list">
        {isLoading ? (
          <div className="session-loading">Loading conversations...</div>
        ) : sessions.length === 0 ? (
          <div className="session-empty">No conversations yet</div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.session_id}
              className={`session-item ${session.session_id === currentSessionId ? 'active' : ''}`}
              onClick={() => onSessionSelect(session.session_id)}
            >
              <div className="session-item-content">
                <div className="session-title">{session.title}</div>
                <div className="session-meta">
                  <span className="session-date">{formatDate(session.updated_at)}</span>
                  {session.message_count > 0 && (
                    <span className="session-count">{session.message_count} messages</span>
                  )}
                </div>
              </div>
              <button
                className="session-delete-button"
                onClick={(e) => handleDeleteSession(session.session_id, e)}
                title="Delete conversation"
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default SessionSidebar;
