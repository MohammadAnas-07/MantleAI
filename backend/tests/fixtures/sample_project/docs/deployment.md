# Deployment

## Docker

Build the image with `docker build -t taskboard .` and run it with the database URL in
`TASKBOARD_DATABASE_URL`.

## Environment variables

- `TASKBOARD_DATABASE_URL`: the PostgreSQL connection string.
- `TASKBOARD_DEBUG`: set to `1` to turn on debug mode.
- `TASKBOARD_ORIGINS`: comma-separated list of allowed CORS origins.

## Backups

Take a nightly `pg_dump` and keep it for 14 days.
