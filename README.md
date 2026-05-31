# Spotify Stats Tracker

A lightweight Python/Flask SpotifyTracker

## Features

- Flask server serving HTML templates and static CSS
- Sample user profile and listening data endpoints

## Run locally

This Flask app renders the UI server-side using Jinja2 templates and the existing CSS found in `static/css/style.css`.

- `backend/` contains the Flask app logic.
- `templates/` contains the server-rendered pages.

1. Create a Python virtual environment

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Start the app

```bash
python app.py
```

4. Open the app in your browser:

```text
http://127.0.0.1:5000
```