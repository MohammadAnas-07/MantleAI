# Architecture

## Backend

The backend is plain Python. `app/tasks.py` holds the task rules, `app/auth.py` the password
hashing and session tokens, and `app/db.py` the connection pool.

## Web

The web app is React with TypeScript. API calls go through `fetchJson` in `src/api/client.ts`,
which retries when the API answers 503.

## Background jobs

Every morning a job finds overdue tasks and sends one reminder email per user.
