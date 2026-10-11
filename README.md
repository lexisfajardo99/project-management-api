# Project Management API (FastAPI + SQLite)

A backend API that helps small teams (student groups, small businesses) keep their projects and tasks in one place and track progress. It follows the pattern of the beginner student starter: Pydantic classes for data, plain SQL against SQLite, and REST endpoints in FastAPI. Business rules live in service classes.

## Run it on Windows

From this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Then open <http://127.0.0.1:8000/docs> to try every endpoint in the browser.

## Project structure

- `main.py` creates the FastAPI app and defines the routes. Routes only receive requests and call a service.
- `app/database.py` opens SQLite connections and creates the tables.
- `app/models.py` defines the Pydantic classes that validate input and output.
- `app/services.py` holds the SQL and the business rules, in service classes (see below).
- `projects.db` is the SQLite file, created the first time the app runs.
- `ai-context.md` is the working-style guide for AI assistants on this project.

## Data model

A project has many tasks. Deleting a project also deletes its tasks.

| Table    | Fields |
|----------|--------|
| projects | id, name, description, status (`planning`, `active`, `on_hold`, `completed`) |
| tasks    | id, project_id (foreign key to projects), title, description, status (`todo`, `in_progress`, `done`), priority (`low`, `medium`, `high`), due_date (`YYYY-MM-DD`, optional) |

## Object-oriented design

- `BaseService` holds what both services share: the database connection factory, record lookups, and the rule that keeps a project's status in step with its tasks. Its helpers are protected (prefixed with `_`) so only the services use them.
- `ProjectService` and `TaskService` inherit from `BaseService` and add their own operations.
- `NotFoundError` and `BusinessRuleError` are custom exceptions. `main.py` turns them into 404 and 409 responses.

## The transactional workflow

Finishing a task affects two tables, so it is done as one transaction.

`POST /tasks/{task_id}/complete`:

1. marks the task as `done`;
2. if every task of the project is now done, sets the project to `completed`;
3. commits both changes together.

If anything fails in between, the connection rolls back and neither the task nor the project is changed. `POST /tasks/{task_id}/reopen` reverses it: the task goes back to `todo`, and a `completed` project becomes `active` again.

Each service method opens one connection, and `database_connection()` commits when the method finishes normally and rolls back on any error.

## Business rules

- A task can only be added to a project that exists, and not to a `completed` project.
- A task cannot be moved into a `completed` project.
- A project cannot be set to `completed` (or created as `completed`) while it has tasks that are not done.
- A `planning` or `active` project becomes `completed` when all its tasks are done, and a `completed` project becomes `active` when one of its tasks is no longer done. An `on_hold` project is never changed automatically.

Rule violations return `409`. Missing records return `404`. Invalid values (for example a status that is not in the list) return `422`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Welcome message |
| GET | `/projects` | List projects, optionally `?search=text` (name or description) |
| GET | `/projects/{project_id}` | Get one project |
| GET | `/projects/{project_id}/summary` | Task counts by status and percent done |
| POST | `/project` | Create a project |
| PUT | `/project/{project_id}` | Update a project |
| DELETE | `/project/{project_id}` | Delete a project and its tasks |
| GET | `/tasks` | List tasks, optionally `?project_id=1&status=todo&search=text` |
| GET | `/tasks/{task_id}` | Get one task |
| POST | `/task` | Create a task (project must exist and not be completed) |
| PUT | `/task/{task_id}` | Update a task |
| DELETE | `/task/{task_id}` | Delete a task |
| POST | `/tasks/{task_id}/complete` | Mark a task done and update its project (one transaction) |
| POST | `/tasks/{task_id}/reopen` | Move a done task back to to-do and reactivate its project |

## Example requests

Create a project:

```json
{ "name": "Website redesign", "description": "New marketing site", "status": "active" }
```

Create a task in it:

```json
{
  "project_id": 1,
  "title": "Draft wireframes",
  "priority": "high",
  "due_date": "2026-11-01"
}
```

Then call `POST /tasks/1/complete` with no body. The response contains the updated task and its project.

## Ideas for extending it

- Add a `members` table and an `assignee_id` on tasks.
- Add `comments` on tasks.
- Add a `GET /tasks?overdue=true` filter using `due_date`.
