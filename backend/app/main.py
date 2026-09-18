from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.gap_reports import gap_reports_router, result_reports_router
from app.api.interviews import router as interviews_router, simulations_router
from app.api.job_imports import router as job_imports_router
from app.api.jobs import router as jobs_router
from app.api.matches import router as matches_router
from app.api.resumes import router as resumes_router
from app.api.taxonomy import router as taxonomy_router
from app.database import check_database_connection

app = FastAPI(title="AI-Driven Smart Hiring Platform")


from fastapi.encoders import jsonable_encoder


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Sanitizes validation errors to ensure sensitive fields never leak into error responses."""
    sensitive_keys = {"secret", "password", "token", "key", "credential", "auth", "secret_ref"}
    sanitized_errors = []
    raw_errors = jsonable_encoder(exc.errors())
    for err in raw_errors:
        err_copy = dict(err)
        loc = [str(x).lower() for x in err.get("loc", ())]
        is_sensitive = any(any(s in part for s in sensitive_keys) for part in loc)
        if is_sensitive and "input" in err_copy:
            err_copy["input"] = "[REDACTED]"
        elif isinstance(err_copy.get("input"), str):
            inp_lower = err_copy["input"].lower()
            if any(inp_lower.startswith(p) for p in ["sk-", "bearer ", "token ", "key-"]):
                err_copy["input"] = "[REDACTED]"
        sanitized_errors.append(err_copy)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": sanitized_errors},
    )

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(jobs_router)
app.include_router(interviews_router)
app.include_router(simulations_router)
app.include_router(job_imports_router)
app.include_router(taxonomy_router)
app.include_router(resumes_router)
app.include_router(matches_router)
app.include_router(gap_reports_router)
app.include_router(result_reports_router)


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
