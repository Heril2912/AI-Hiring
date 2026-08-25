from fastapi import FastAPI

app = FastAPI(title="AI-Driven Smart Hiring Platform")


@app.get("/api/v1/health")
def health_check():
    """Confirms the API process is running."""
    return {"status": "healthy", "service": "ai-hiring-backend"}
