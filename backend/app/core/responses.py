from typing import Any


def ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "data": data, "error": None}


def err(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "error",
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
    }
