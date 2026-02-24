import logging
import logging.config
import os

from app.core.config import settings


def setup_logging() -> None:
    level = settings.log_level.upper()
    requested_path = settings.log_file_path
    fallback_path = os.path.join("logs", "backend.log")
    file_path = requested_path

    try:
        os.makedirs(os.path.dirname(requested_path), exist_ok=True)
        with open(requested_path, "a", encoding="utf-8"):
            pass
    except OSError:
        file_path = fallback_path
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "level": level,
                "filename": file_path,
                "maxBytes": 10_000_000,
                "backupCount": 5,
            },
        },
        "loggers": {
            "": {"handlers": ["console", "file"], "level": level},
            "uvicorn": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "vch.http": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "vch.metrics": {"handlers": ["console", "file"], "level": level, "propagate": False},
        },
    }
    logging.config.dictConfig(logging_config)
