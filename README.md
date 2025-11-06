# Agentic E-Commerce Assistant

An intelligent, LLM-powered chat assistant for e-commerce websites specializing in appliance parts.
Built with an agentic architecture featuring function calling, the assistant autonomously scrapes real-time product data using Playwright MCP and BeautifulSoup, interprets user intent via the DeepSeek LLM, and generates context-aware, high-accuracy responses.

## Features

### Core Capabilities

- **Agentic Architecture**: LLM-driven decision making using function calling (ToolAgent) that autonomously decides when to scrape information
- **Intelligent Web Scraping**: On-demand scraping using Playwright browser automation and BeautifulSoup for data extraction
- **DeepSeek LLM Integration**: Powered by DeepSeek language model for intelligent, context-aware responses
- **Product Information Retrieval**: Fetches product descriptions, installation guides, compatibility data, and specifications
- **Source Attribution**: Automatically tracks and provides source URLs for all scraped information

### Session & Conversation Management

- **Multi-Session Support**: Create and manage multiple conversation sessions
- **In-Memory Caching**: Fast retrieval of recent conversation context (last 5 messages) for LLM processing
- **Session Management API**: Create, list, delete, and clear sessions programmatically

### Feedback & Improvement System

- **User Feedback Collection**: Thumbs up/down rating system for responses
- **Feedback Analysis**: Analyzes feedback patterns to identify improvement areas
- **Adaptive Prompts**: Automatically enhances system prompts based on user feedback

### Frontend Features

- **Modern React UI**: Clean, responsive chat interface
- **Session Sidebar**: Manage multiple conversation sessions
- **Source Links**: Clickable source URLs in responses
- **Feedback UI**: Easy-to-use feedback buttons for each response

### Scope Management

- **Focused Expertise**: Specializes in Refrigerator and Dishwasher parts
- **Out-of-Scope Detection**: Automatically identifies and politely redirects off-topic queries



## Prerequisites

- Python 3.8+
- Node.js 14+
- npm or yarn
- Playwright browsers

## Installation

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

4. Create a `.env` file in the project root with your DeepSeek API key:
```env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
PARTSELECT_BASE_URL=https://www.partselect.com
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

## Running the Application

### Start the Backend

From the `backend/` directory:

```bash
python run.py
```

The backend will start on `http://localhost:8000` by default.

### Start the Frontend

From the `frontend/` directory:

```bash
npm start
```

The frontend will start on `http://localhost:3000` and automatically open in your browser.



## Configuration

### Backend Configuration

Edit `backend/app/config.py` or set environment variables:

- `DEEPSEEK_API_KEY`: Your DeepSeek API key (required)
- `DEEPSEEK_BASE_URL`: DeepSeek API endpoint (default: https://api.deepseek.com)
- `DEEPSEEK_MODEL`: Model name (default: deepseek-chat)
- `PARTSELECT_BASE_URL`: Target website URL (default: https://www.partselect.com)
- `API_PORT`: Backend port (default: 8000)
- `LOG_LEVEL`: Logging level (default: INFO)

### Frontend Configuration

The frontend API endpoint is configured in `frontend/src/api/api.js`. Default is `http://localhost:8000`.


## License

This project is open source and available under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues, questions, or contributions, please open an issue on GitHub.
