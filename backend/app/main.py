from fastapi import FastAPI, Response, status
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.job_imports import router as job_imports_router
from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router
from app.api.taxonomy import router as taxonomy_router
from app.database import check_database_connection

app = FastAPI(title="AI-Driven Smart Hiring Platform")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(jobs_router)
app.include_router(job_imports_router)
app.include_router(taxonomy_router)
app.include_router(resumes_router)


@app.get("/api/v1/health")
def health_check(response: Response):
    """Confirms the API process is running and checks database connectivity."""
    if check_database_connection():
        return {
            "status": "healthy",
            "service": "ai-hiring-backend",
            "database": "connected",
        }

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "degraded",
        "service": "ai-hiring-backend",
        "database": "disconnected",
    }
