from fastapi import FastAPI
from backend.database import engine,Base
import backend.models

app=FastAPI(
    title="Sales pipeline API",
    description="Backend API for Sales Data Pipeline Dashboard",
    version="1.0.0"
)

Base.metadata.create_all(bind=engine)

@app.get("/")
def health_check():
    return {
        "status":"OK",
        "message":"Sales Data Pipeline API is running",
        "version":"1.0.0"
    }