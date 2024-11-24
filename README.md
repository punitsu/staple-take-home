# OpenAI Proxy Service

A Flask-based RESTful service that provides a proxy to OpenAI's GPT API.

## Prerequisites

- Python 3.10+
- OpenAI API key

## Installation

1. Clone the repository:
```bash
git clone https://github.com/punitsu/staple-take-home.git
cd staple-take-home
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_api_key_here
DEBUG=False
```

## Database Setup

The application automatically initializes an SQLite database with the following schema:

- `users` table: Stores user information and rate limiting data
- `conversations` table: Logs all conversations with tokens used

## API Endpoints

### POST `/openai-completion`

Proxies requests to OpenAI's Chat Completion API.

#### Request Headers
- `X-User-ID` (optional): User identifier. If not provided, a new user ID will be generated.
- `Content-Type`: Must be `application/json`

#### Request Body
```json
{
    "prompt": "Your message here"
}
```

#### Response
```json
{
    "user_id": "generated_or_provided_user_id",
    "response": "API response content",
    "tokens_used": 123
}
```

#### CURL Example
```bash
curl -X POST http://localhost:5000/openai-completion \
    -H "Content-Type: application/json" \
    -d '{"prompt": "Your message here"}'
```

#### Rate Limiting
- 10 requests per minute per user
- Returns 429 status code when limit is exceeded

## Running the Application

Start the server:
```bash
python main.py
```

The application will run on `http://localhost:5000` by default.

## Development

To run in debug mode, set in `.env`:
```bash
DEBUG=True
```
