from flask import Flask, request, jsonify
import sqlite3
import os
import uuid6
from datetime import datetime
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def init_db():
    with sqlite3.connect("chat_history.db") as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                minute_start DATETIME,
                request_count INTEGER DEFAULT 0
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                tokens_used INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_user 
            ON conversations(user_id)
        """
        )

        conn.commit()


def check_and_update_rate_limit(user_id):
    with sqlite3.connect("chat_history.db") as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT minute_start, request_count 
            FROM users 
            WHERE user_id = ?
        """,
            (user_id,),
        )

        result = cursor.fetchone()
        current_time = datetime.utcnow()

        if result:
            minute_start, count = result
            minute_start = (
                datetime.fromisoformat(minute_start) if minute_start else None
            )

            # If it's a new minute or first request, reset counter
            if not minute_start or (current_time - minute_start).total_seconds() >= 60:
                cursor.execute(
                    """
                    UPDATE users 
                    SET minute_start = ?, request_count = 1 
                    WHERE user_id = ?
                """,
                    (current_time.isoformat(), user_id),
                )
                conn.commit()
                return True

            # If within same minute, increment counter if under limit
            if count < 10:
                cursor.execute(
                    """
                    UPDATE users 
                    SET request_count = request_count + 1 
                    WHERE user_id = ?
                """,
                    (user_id,),
                )
                conn.commit()
                return True

            return False


def get_or_create_user_id():
    user_id = request.headers.get("X-User-ID")
    current_time = datetime.utcnow()
    with sqlite3.connect("chat_history.db") as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute(
                """
                SELECT user_id 
                FROM users 
                WHERE user_id = ?
            """,
                [user_id],
            )
            result = cursor.fetchone()

            if not result:
                return None

        else:
            user_id = str(uuid6.uuid7())
            cursor.execute(
                """
                INSERT INTO users (user_id, minute_start, request_count)
                VALUES (?, ?, 0)
            """,
                (user_id, current_time.isoformat()),
            )
            conn.commit()

    return user_id


def log_conversation(user_id, prompt, response_data):
    with sqlite3.connect("chat_history.db") as conn:
        cursor = conn.cursor()

        tokens_used = response_data.get("usage", {}).get("total_tokens", 0)
        response_text = (
            response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

        cursor.execute(
            """
            INSERT INTO conversations (user_id, prompt, response, tokens_used)
            VALUES (?, ?, ?, ?)
        """,
            (user_id, prompt, response_text, tokens_used),
        )

        conn.commit()


@app.route("/openai-completion", methods=["POST"])
def openai_completion():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json()
    prompt = data.get("prompt")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    user_id = get_or_create_user_id()

    if not user_id:
        return jsonify({
            "error": "Invalid user ID",
            "message": "The provided X-User-ID is not valid. Remove the header to generate a new user ID."
        }), 401


    if not check_and_update_rate_limit(user_id):
        return (
            jsonify(
                {
                    "error": "Rate limit exceeded",
                    "message": "Maximum 10 requests per minute allowed",
                }
            ),
            429,
        )

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 150,
            },
        )

        response_data = response.json()

        if response.status_code != 200:
            return (
                jsonify(
                    {
                        "error": "OpenAI API error",
                        "message": response_data.get("error", {}).get(
                            "message", "Unknown error"
                        ),
                    }
                ),
                response.status_code,
            )

        log_conversation(user_id, prompt, response_data)

        return jsonify(
            {
                "user_id": user_id,
                "response": response_data["choices"][0]["message"]["content"],
                "tokens_used": response_data.get("usage", {}).get("total_tokens", 0),
            }
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        return jsonify({"error": "Failed to communicate with OpenAI API"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=os.getenv("DEBUG", "False") == "True")
