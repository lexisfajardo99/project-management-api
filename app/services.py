"""Business logic and SQL for projects and tasks, organized as service classes.

BaseService holds what both services share (the connection factory, record
lookups, and the rule that keeps a project's status in step with its tasks).
ProjectService and TaskService inherit from it and add their own operations.

Every public method opens exactly one database connection. database_connection()
commits when the block ends normally and rolls back if an exception is raised,
so every method is a single all-or-nothing transaction. This matters most for
complete_task and reopen_task, which change two tables in that one transaction.
"""

from app.models import ProjectInput, TaskInput

PROJECT_COLUMNS = "id, name, description, status"
TASK_COLUMNS = "id, project_id, title, description, status, priority, due_date"


class NotFoundError(Exception):
    """Raised when a requested project or task does not exist."""


class BusinessRuleError(Exception):
    """Raised when a request is valid but breaks a rule of the system."""


class BaseService:
    """Shared behavior for the project and task services."""

    def __init__(self, database_connection):
        self._database_connection = database_connection

    @staticmethod
    def _like_pattern(term):
        """Build a LIKE pattern that treats the search term as plain text."""

        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _require_project(connection, project_id):
        row = connection.execute(
            f"SELECT {PROJECT_COLUMNS} FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Project not found")
        return dict(row)

    @staticmethod
    def _require_task(connection, task_id):
        row = connection.execute(
            f"SELECT {TASK_COLUMNS} FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Task not found")
        return dict(row)

    @staticmethod
    def _sync_project_status(connection, project_id):
        """Keep a project's status in step with the state of its tasks.

        - A planning or active project whose tasks are all done becomes completed.
        - A completed project that has an unfinished task becomes active again.
        - An on_hold project is never changed automatically.
        """

        counts = connection.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0) AS done "
            "FROM tasks WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        project = connection.execute(
            "SELECT status FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if project is None:
            return
        total, done = counts["total"], counts["done"]
        if total > 0 and done == total and project["status"] in ("planning", "active"):
            new_status = "completed"
        elif project["status"] == "completed" and done < total:
            new_status = "active"
        else:
            return
        connection.execute(
            "UPDATE projects SET status = ? WHERE id = ?", (new_status, project_id)
        )


class ProjectService(BaseService):
    """Operations on projects."""

    def list_projects(self, search=None):
        query = f"SELECT {PROJECT_COLUMNS} FROM projects"
        parameters = []
        if search and search.strip():
            pattern = self._like_pattern(search.strip())
            query += (
                " WHERE (name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"
            )
            parameters += [pattern, pattern]
        query += " ORDER BY id"
        with self._database_connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id):
        with self._database_connection() as connection:
            return self._require_project(connection, project_id)

    def create_project(self, project_input: ProjectInput):
        if project_input.status == "completed":
            raise BusinessRuleError(
                "A new project has no finished tasks yet, so it cannot start as completed"
            )
        with self._database_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO projects (name, description, status) VALUES (?, ?, ?)",
                (project_input.name, project_input.description, project_input.status),
            )
            return self._require_project(connection, cursor.lastrowid)

    def update_project(self, project_id, project_input: ProjectInput):
        with self._database_connection() as connection:
            self._require_project(connection, project_id)
            if project_input.status == "completed":
                unfinished = connection.execute(
                    "SELECT COUNT(*) FROM tasks "
                    "WHERE project_id = ? AND status != 'done'",
                    (project_id,),
                ).fetchone()[0]
                if unfinished:
                    raise BusinessRuleError(
                        f"Cannot complete the project: {unfinished} task(s) are not done"
                    )
            connection.execute(
                "UPDATE projects SET name = ?, description = ?, status = ? WHERE id = ?",
                (
                    project_input.name,
                    project_input.description,
                    project_input.status,
                    project_id,
                ),
            )
            return self._require_project(connection, project_id)

    def delete_project(self, project_id):
        """Delete a project and, through ON DELETE CASCADE, its tasks."""

        with self._database_connection() as connection:
            self._require_project(connection, project_id)
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def get_summary(self, project_id):
        """Count a project's tasks by status."""

        with self._database_connection() as connection:
            self._require_project(connection, project_id)
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM tasks "
                "WHERE project_id = ? GROUP BY status",
                (project_id,),
            ).fetchall()
        counts = {"todo": 0, "in_progress": 0, "done": 0}
        for row in rows:
            counts[row["status"]] = row["total"]
        total = sum(counts.values())
        percent_done = round(counts["done"] / total * 100) if total else 0
        return {"tasks": counts, "total": total, "percent_done": percent_done}


class TaskService(BaseService):
    """Operations on tasks, including the complete and reopen workflow."""

    @staticmethod
    def _date_to_text(value):
        """SQLite has no date type, so dates are stored as ISO text (YYYY-MM-DD)."""

        return value.isoformat() if value else None

    def list_tasks(self, project_id=None, status=None, search=None):
        query = f"SELECT {TASK_COLUMNS} FROM tasks"
        conditions = []
        parameters = []
        if project_id is not None:
            conditions.append("project_id = ?")
            parameters.append(project_id)
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status)
        if search and search.strip():
            pattern = self._like_pattern(search.strip())
            conditions.append(
                "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"
            )
            parameters += [pattern, pattern]
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"
        with self._database_connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id):
        with self._database_connection() as connection:
            return self._require_task(connection, task_id)

    def create_task(self, task_input: TaskInput):
        with self._database_connection() as connection:
            project = self._require_project(connection, task_input.project_id)
            if project["status"] == "completed":
                raise BusinessRuleError("Cannot add a task to a completed project")
            cursor = connection.execute(
                "INSERT INTO tasks "
                "(project_id, title, description, status, priority, due_date) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task_input.project_id,
                    task_input.title,
                    task_input.description,
                    task_input.status,
                    task_input.priority,
                    self._date_to_text(task_input.due_date),
                ),
            )
            return self._require_task(connection, cursor.lastrowid)

    def update_task(self, task_id, task_input: TaskInput):
        with self._database_connection() as connection:
            existing = self._require_task(connection, task_id)
            target = self._require_project(connection, task_input.project_id)
            moving = task_input.project_id != existing["project_id"]
            if moving and target["status"] == "completed":
                raise BusinessRuleError("Cannot move a task into a completed project")
            connection.execute(
                "UPDATE tasks SET project_id = ?, title = ?, description = ?, "
                "status = ?, priority = ?, due_date = ? WHERE id = ?",
                (
                    task_input.project_id,
                    task_input.title,
                    task_input.description,
                    task_input.status,
                    task_input.priority,
                    self._date_to_text(task_input.due_date),
                    task_id,
                ),
            )
            self._sync_project_status(connection, existing["project_id"])
            if moving:
                self._sync_project_status(connection, task_input.project_id)
            return self._require_task(connection, task_id)

    def delete_task(self, task_id):
        with self._database_connection() as connection:
            existing = self._require_task(connection, task_id)
            connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._sync_project_status(connection, existing["project_id"])

    def complete_task(self, task_id):
        """Mark a task done and update its project, as one transaction.

        If this was the project's last unfinished task, the project becomes
        completed in the same transaction. If anything fails, neither the task
        nor the project is changed.
        """

        with self._database_connection() as connection:
            task = self._require_task(connection, task_id)
            if task["status"] == "done":
                raise BusinessRuleError("Task is already done")
            connection.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,)
            )
            self._sync_project_status(connection, task["project_id"])
            return {
                "task": self._require_task(connection, task_id),
                "project": self._require_project(connection, task["project_id"]),
            }

    def reopen_task(self, task_id):
        """Move a done task back to to-do, and reactivate its project if needed."""

        with self._database_connection() as connection:
            task = self._require_task(connection, task_id)
            if task["status"] != "done":
                raise BusinessRuleError("Only a done task can be reopened")
            connection.execute(
                "UPDATE tasks SET status = 'todo' WHERE id = ?", (task_id,)
            )
            self._sync_project_status(connection, task["project_id"])
            return {
                "task": self._require_task(connection, task_id),
                "project": self._require_project(connection, task["project_id"]),
            }
