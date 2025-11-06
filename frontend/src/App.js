import React, { useEffect, useState, useRef } from "react";
import "./App.css";
import ChatWindow from "./components/ChatWindow";
import SessionSidebar from "./components/SessionSidebar";
import { checkHealth, createSession, listSessions } from "./api/api";

function App() {
  const [isConnected, setIsConnected] = useState(null); // null = checking, true/false = status
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0); // Trigger to refresh sidebar
  const hasInitialized = useRef(false);

  useEffect(() => {
    // Check API connection on mount and initialize session once
    const initializeApp = async () => {
      if (hasInitialized.current) return; // Prevent duplicate initialization
      hasInitialized.current = true;
      
      const healthy = await checkHealth();
      setIsConnected(healthy);
      
      // If connected, check for existing sessions first
      if (healthy) {
        try {
          const sessions = await listSessions();
          if (sessions && sessions.length > 0) {
            // Use the most recent session (first in the list, as they're sorted by updated_at DESC)
            setCurrentSessionId(sessions[0].session_id);
          } else {
            // No existing sessions, create a new one
            const sessionId = await createSession();
            if (sessionId) {
              setCurrentSessionId(sessionId);
            }
          }
        } catch (error) {
          console.error("Error initializing sessions:", error);
        }
      }
    };
    
    initializeApp();
    
    // Periodically check connection (but don't create sessions)
    // Reduced frequency to 60 seconds to reduce API calls
    const interval = setInterval(async () => {
      const healthy = await checkHealth();
      setIsConnected(healthy);
    }, 60000); // Every 60 seconds
    
    return () => clearInterval(interval);
  }, []);

  const handleSessionSelect = (sessionId) => {
    setCurrentSessionId(sessionId);
  };

  const handleNewSession = (sessionId) => {
    setCurrentSessionId(sessionId);
    setRefreshTrigger(prev => prev + 1); // Trigger sidebar refresh
  };

  const handleSessionUpdate = () => {
    setRefreshTrigger(prev => prev + 1); // Trigger sidebar refresh after message
  };

  return (
    <div className="App">
      <SessionSidebar
        currentSessionId={currentSessionId}
        onSessionSelect={handleSessionSelect}
        onNewSession={handleNewSession}
        refreshTrigger={refreshTrigger}
      />
      <div className="app-content">
        <header className="app-header">
          <div className="header-content">
            <div className="header-brand">
              <h1 className="brand-title">PartSelect</h1>
              <span className="brand-subtitle">Chat Assistant</span>
            </div>
            <div className="header-status">
              {isConnected === null && (
                <span className="status-indicator status-checking">Checking...</span>
              )}
              {isConnected === true && (
                <span className="status-indicator status-online">
                  <span className="status-dot"></span>
                  Online
                </span>
              )}
              {isConnected === false && (
                <span className="status-indicator status-offline">
                  <span className="status-dot"></span>
                  Offline
                </span>
              )}
            </div>
          </div>
        </header>
        <main className="app-main">
          <ChatWindow
            sessionId={currentSessionId}
            onSessionChange={handleNewSession}
            onMessageSent={handleSessionUpdate}
          />
        </main>
        {isConnected === false && (
          <div className="connection-warning">
            ⚠️ Unable to connect to the server. Please ensure the backend is running.
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
