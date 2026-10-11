"""Data models used to validate API input and output.

These classes only describe the shape of the data. The SQL and the business
rules live in app/services.py.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["planning", "active", "on_hold", "completed"]
TaskStatus = Literal["todo", "in_progress", "done"]
TaskPriority = Literal["low", "medium", "high"]


class ProjectInput(BaseModel):
    """Fields a client can send when creating or updating a project."""

    name: str = Field(min_length=1)
    description: str = ""
    status: ProjectStatus = "planning"


class Project(ProjectInput):
    """A project record returned by the API."""

    id: int


class TaskInput(BaseModel):
    """Fields a client can send when creating or updating a task."""

    project_id: int
    title: str = Field(min_length=1)
    description: str = ""
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    due_date: date | None = None


class Task(TaskInput):
    """A task record returned by the API."""

    id: int
