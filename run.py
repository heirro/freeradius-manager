"""Entry point — jalankan langsung: python run.py"""
import uvicorn
from api.config import get_settings


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
