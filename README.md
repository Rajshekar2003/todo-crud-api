# Task API

A CRUD API for managing a to-do list, built with FastAPI, running against a containerized PostgreSQL database via Docker Compose. Built as part of the FlyRank Backend Track internship — three storage stages: in-memory (Week 2), SQLite (Week 3), and now Postgres in Docker.

## What this is
A REST API supporting full CRUD on tasks: create, read, update, and delete. Data is stored in a real PostgreSQL database running in a Docker container, so it survives both server restarts and full container teardowns. The whole stack (app + database) starts with a single command.

## How to run it

1. Copy the example environment file:
```bash
   cp .env.example .env
```
2. Start everything with Docker Compose:
```bash
   docker compose up
```
3. Visit `http://localhost:8000/docs` for the interactive Swagger docs.

That's it — no local Python install, no manual database setup. Docker builds the app image and starts Postgres automatically, creates the `tasks` table, and seeds 3 example tasks on first run.

## Environment variables
See `.env.example` for the required variable:
```
DATABASE_URL=postgres://postgres:dev@localhost:5432/tasks
```
`.env` is git-ignored — never commit real secrets. Inside Docker Compose, the app reaches the database using the service name `db` instead of `localhost` (see `compose.yaml`).

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | / | API info |
| GET | /health | Health check |
| GET | /tasks | List all tasks |
| GET | /tasks/{id} | Get one task |
| POST | /tasks | Create a task |
| PUT | /tasks/{id} | Update a task |
| DELETE | /tasks/{id} | Delete a task |

## Example request

```
$ curl -i http://localhost:8000/tasks
HTTP/1.1 200 OK
content-type: application/json

[{"id":1,"title":"Buy milk","done":false},{"id":2,"title":"Walk the dog","done":true},{"id":3,"title":"Finish assignment","done":false},{"id":4,"title":"Test persistence","done":false}]
```

## Swagger UI

![Swagger UI](swagger-screenshot.png)

## Data in Postgres

Verified directly inside the running container:
```
docker exec -it todo-api-db-1 psql -U postgres -d tasks -c "SELECT * FROM tasks;"
```

![Postgres data](docker-db-screenshot.png)

## Persistence proof
Created a task, ran `docker compose down` (fully removing both containers), then `docker compose up` again — the task was still there. This confirms the named volume (`taskdata`) keeps the database's actual data safe independent of the containers' lifecycle.

## Notes
- All queries use parameterized placeholders (`%s`) to safely handle user input.
- The database and table are created automatically on first run; 3 example tasks are seeded only when the table is empty.
- This is the third storage engine this project has used (in-memory → SQLite → Postgres) with the API itself never changing — proof that storage is just an implementation detail underneath a stable interface.