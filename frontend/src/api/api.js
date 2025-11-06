const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * Send a chat message to the backend API
 * @param {string} userQuery - The user's message
 * @param {string|null} sessionId - Optional session ID for continuing conversation
 * @returns {Promise<Object>} Response with message and session ID
 */
export const getAIMessage = async (userQuery, sessionId = null) => {
  try {
    const requestBody = {
      message: userQuery
    };
    
    // Include session_id if provided (for continuing conversation)
    if (sessionId) {
      requestBody.session_id = sessionId;
    }

    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('API Error:', response.status, errorText);
      throw new Error(`API error: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    
    // Validate response
    if (!data || !data.response) {
      console.error('Invalid API response:', data);
      throw new Error('Invalid response from server');
    }
    
    return {
      role: "assistant",
      content: data.response,
      session_id: data.session_id, // Return session_id for next request
      intent: data.intent,
      entities: data.entities || {},
      sources_used: data.sources_used,
      source_urls: data.source_urls || [],
      metadata: {
        hasProductInfo: data.entities?.part_numbers?.length > 0,
        hasModelInfo: data.entities?.model_numbers?.length > 0,
        applianceType: data.entities?.appliance_type
      }
    };
  } catch (error) {
    console.error('Error calling API:', error);
    // Return error message instead of placeholder
    return {
      role: "assistant",
      content: `I'm having trouble connecting to the server. Please make sure the backend is running at ${API_BASE_URL}. Error: ${error.message}`,
      error: true
    };
  }
};

/**
 * List all sessions
 */
export const listSessions = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/sessions`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    return data.sessions || [];
  } catch (error) {
    console.error('Error listing sessions:', error);
    return [];
  }
};

/**
 * Get session details
 */
export const getSession = async (sessionId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error getting session:', error);
    return null;
  }
};

/**
 * Get session history
 */
export const getSessionHistory = async (sessionId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/history`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    return data.history || [];
  } catch (error) {
    console.error('Error getting session history:', error);
    return [];
  }
};

/**
 * Create a new session
 */
export const createSession = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/sessions/new`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    return data.session_id;
  } catch (error) {
    console.error('Error creating session:', error);
    return null;
  }
};

/**
 * Delete a session
 */
export const deleteSession = async (sessionId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return true;
  } catch (error) {
    console.error('Error deleting session:', error);
    return false;
  }
};

/**
 * Submit feedback for a message
 * @param {string} sessionId - Session ID
 * @param {string} messageContent - The assistant message content
 * @param {string} rating - 'thumbs_up' or 'thumbs_down'
 */
export const submitFeedback = async (sessionId, messageContent, rating) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        message_content: messageContent,
        rating: rating
      })
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error submitting feedback:', error);
    throw error;
  }
};

/**
 * Check API health
 */
export const checkHealth = async () => {
  try {
    console.log(`🔍 Checking health at: ${API_BASE_URL}/api/health`);
    
    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
    
    const response = await fetch(`${API_BASE_URL}/api/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    const isOk = response.ok;
    console.log(`✅ Health check response: ${response.status} ${response.statusText}`);
    
    if (isOk) {
      const data = await response.json();
      console.log('Health check data:', data);
    }
    
    return isOk;
  } catch (error) {
    console.error('❌ Health check failed:', error);
    console.error('Error details:', {
      name: error.name,
      message: error.message,
      apiUrl: `${API_BASE_URL}/api/health`
    });
    
    // Check if it's a network error
    if (error.name === 'AbortError') {
      console.error('Request timed out after 5 seconds');
    } else if (error.message.includes('Failed to fetch')) {
      console.error('Network error - is the backend running?');
    }
    
    return false;
  }
};
