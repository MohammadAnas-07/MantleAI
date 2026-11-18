# Taskboard

A small task tracker used as a test fixture for Mantle's indexing.

## Setup

Install Python 3.12 and Node 20. Then install the backend with `pip install -e backend` and the
web app with `npm install` inside `web`.

## Running

Start the API with `python -m app.main` and the web app with `npm run dev`. The web app expects
the API on port 8000.

## Tests

Run `pytest` in `backend`.
