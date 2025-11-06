# Backend

FastAPI-based backend for the agentic e-commerce assistant.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

3. Create `.env` file in project root:
```env
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
PARTSELECT_BASE_URL=https://www.partselect.com
API_PORT=8000
LOG_LEVEL=INFO
```

## Running


```bash
python run.py
```
Starts on `http://localhost:8000`

## API Documentation

Interactive API docs available at `http://localhost:8000/docs` when server is running.
