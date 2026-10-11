"""Create the FastAPI app and connect its routes."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import database_connection, initialize_database
from app.models import ProjectInput, TaskInput, TaskStatus
from app.services import (
    BusinessRuleError,
    NotFoundError,
    ProjectService,
    TaskService,
)

app = FastAPI(title="Project Management API")

project_service = ProjectService(database_connection)
task_service = TaskService(database_connection)


@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, error: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(BusinessRuleError)
def handle_business_rule(request: Request, error: BusinessRuleError):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.get("/")
def home():
    return {"message": "Welcome! Visit /docs to try the API."}


# Projects


@app.get("/projects")
def get_projects(search: str | None = None):
    return {"projects": project_service.list_projects(search=search)}


@app.get("/projects/{project_id}")
def get_project(project_id: int):
    return {"project": project_service.get_project(project_id)}


@app.get("/projects/{project_id}/summary")
def get_project_summary(project_id: int):
    return {"summary": project_service.get_summary(project_id)}


@app.post("/project", status_code=201)
def create_project(project: ProjectInput):
    return {"project": project_service.create_project(project)}


@app.put("/project/{project_id}")
def edit_project(project_id: int, project: ProjectInput):
    return {"project": project_service.update_project(project_id, project)}


@app.delete("/project/{project_id}")
def delete_project(project_id: int):
    project_service.delete_project(project_id)
    return {"message": "Project and its tasks deleted successfully"}


# Tasks


@app.get("/tasks")
def get_tasks(
    project_id: int | None = None,
    status: TaskStatus | None = None,
    search: str | None = None,
):
    return {
        "tasks": task_service.list_tasks(
            project_id=project_id, status=status, search=search
        )
    }


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    return {"task": task_service.get_task(task_id)}


@app.post("/task", status_code=201)
def create_task(task: TaskInput):
    return {"task": task_service.create_task(task)}


@app.put("/task/{task_id}")
def edit_task(task_id: int, task: TaskInput):
    return {"task": task_service.update_task(task_id, task)}


@app.delete("/task/{task_id}")
def delete_task(task_id: int):
    task_service.delete_task(task_id)
    return {"message": "Task deleted successfully"}


# Workflow: each of these changes a task and its project in one transaction


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: int):
    return task_service.complete_task(task_id)


@app.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: int):
    return task_service.reopen_task(task_id)


initialize_database()
