import React, { useState, useEffect, useRef } from "react";
import "./ChatWindow.css";
import { getAIMessage, getSessionHistory, createSession, submitFeedback } from "../api/api";
import { marked } from "marked";

const defaultMessage = [{
  role: "assistant",
  content: "Hi! I'm your PartSelect assistant. I can help you find parts, check compatibility, get installation instructions, and troubleshoot your appliances. How can I help you today?"
}];

function ChatWindow({ sessionId, onSessionChange, onMessageSent }) {
  const [messages, setMessages] = useState(defaultMessage);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [copiedMessageIndex, setCopiedMessageIndex] = useState(null);
  const [feedbackRatings, setFeedbackRatings] = useState({}); // {messageIndex: 'thumbs_up' | 'thumbs_down'}
  const messagesEndRef = useRef(null);

  // Load conversation history when sessionId changes
  useEffect(() => {
    const loadSessionHistory = async () => {
      if (sessionId) {
        setIsLoadingHistory(true);
        try {
          const history = await getSessionHistory(sessionId);
          if (history && history.length > 0) {
            // Convert history format to message format
            const formattedMessages = history.map(msg => ({
              role: msg.role,
              content: msg.content
            }));
            setMessages(formattedMessages);
          } else {
            // No history, reset to default message
            setMessages(defaultMessage);
          }
        } catch (error) {
          console.error("Error loading session history:", error);
          setMessages(defaultMessage);
        } finally {
          setIsLoadingHistory(false);
        }
      } else {
        // No session, reset to default
        setMessages(defaultMessage);
      }
      
      // Reset feedback state when switching sessions
      setFeedbackRatings({});
      setCopiedMessageIndex(null);
    };

    loadSessionHistory();
  }, [sessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userQuery = input.trim();
    
    // If no session, create one first
    let currentSessionId = sessionId;
    if (!currentSessionId) {
      currentSessionId = await createSession();
      if (currentSessionId && onSessionChange) {
        onSessionChange(currentSessionId);
      }
    }
    
    // Add user message immediately
    const userMessage = { role: "user", content: userQuery };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Call API with session_id
      // Backend will manage conversation history server-side
      const assistantMessage = await getAIMessage(userQuery, currentSessionId);
      
      // Only add assistant message if we got a valid response
      if (assistantMessage && assistantMessage.content) {
        setMessages(prevMessages => [...prevMessages, assistantMessage]);
        
        // Update session_id from response if it changed (shouldn't, but just in case)
        if (assistantMessage.session_id && assistantMessage.session_id !== currentSessionId && onSessionChange) {
          onSessionChange(assistantMessage.session_id);
        }
        
        // Notify parent that a message was sent (to refresh sidebar for title updates)
        if (onMessageSent) {
          onMessageSent();
        }
      } else {
        throw new Error('No response from server');
      }
    } catch (error) {
      console.error("Error sending message:", error);
      setMessages(prevMessages => [...prevMessages, {
        role: "assistant",
        content: `I'm sorry, I encountered an error processing your request. Please check that the backend server is running at ${process.env.REACT_APP_API_URL || 'http://localhost:8000'}.`,
        error: true
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopyMessage = async (messageContent, messageIndex) => {
    try {
      // Copy plain text content (strip HTML tags for clipboard)
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = messageContent;
      const plainText = tempDiv.textContent || tempDiv.innerText || '';
      
      await navigator.clipboard.writeText(plainText);
      
      // Show feedback
      setCopiedMessageIndex(messageIndex);
      setTimeout(() => {
        setCopiedMessageIndex(null);
      }, 2000);
    } catch (error) {
      console.error('Failed to copy message:', error);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = messageContent.replace(/<[^>]*>/g, '');
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        setCopiedMessageIndex(messageIndex);
        setTimeout(() => {
          setCopiedMessageIndex(null);
        }, 2000);
      } catch (err) {
        console.error('Fallback copy failed:', err);
      }
      document.body.removeChild(textArea);
    }
  };

  const handleFeedback = async (messageIndex, rating) => {
    if (!sessionId || !messages[messageIndex]) return;
    
    const message = messages[messageIndex];
    
    // Update UI immediately
    setFeedbackRatings(prev => ({
      ...prev,
      [messageIndex]: rating
    }));
    
    try {
      // Send feedback to backend
      await submitFeedback(sessionId, message.content, rating);
      console.log(`Feedback submitted: ${rating} for message ${messageIndex}`);
    } catch (error) {
      console.error('Error submitting feedback:', error);
      // Revert UI state on error
      setFeedbackRatings(prev => {
        const newState = { ...prev };
        delete newState[messageIndex];
        return newState;
      });
    }
  };

  if (isLoadingHistory) {
    return (
      <div className="chat-window-container">
        <div className="messages-container">
          <div className="loading-history">Loading conversation...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-window-container">
      <div className="messages-container">
        {messages.map((message, index) => (
          <div key={index} className={`${message.role}-message-container`}>
            <div className={`message ${message.role}-message`}>
              <div 
                className="message-content"
                dangerouslySetInnerHTML={{
                  __html: marked(message.content).replace(/<p>|<\/p>/g, "")
                }}
              />
              {message.role === 'assistant' && (
                <div className="message-actions">
                    <button
                      className={`action-button copy-action ${copiedMessageIndex === index ? 'active' : ''}`}
                      onClick={() => handleCopyMessage(message.content, index)}
                      title={copiedMessageIndex === index ? "Copied!" : "Copy message"}
                      aria-label="Copy message"
                    >
                      {copiedMessageIndex === index ? (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      ) : (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" strokeLinecap="round" strokeLinejoin="round"/>
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      )}
                    </button>
                  <button
                    className={`action-button feedback-button ${feedbackRatings[index] === 'thumbs_up' ? 'active' : ''}`}
                    onClick={() => handleFeedback(index, 'thumbs_up')}
                    title="Good response"
                    aria-label="Good response"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                  <button
                    className={`action-button feedback-button ${feedbackRatings[index] === 'thumbs_down' ? 'active' : ''}`}
                    onClick={() => handleFeedback(index, 'thumbs_down')}
                    title="Bad response"
                    aria-label="Bad response"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div className="assistant-message-container">
            <div className="message assistant-message loading-message">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="input-area">
        <div className="input-wrapper">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about parts, compatibility, installation, or troubleshooting..."
            className="chat-input"
            disabled={isLoading}
          />
          <button 
            className="send-button" 
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
          >
            {isLoading ? "..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatWindow;
