import hmac
import os

from fastapi import Header, HTTPException, status


def app_environment() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def validate_production_config() -> None:
    """Fail startup when production administrative access is unconfigured."""
    if app_environment() != "production":
        return

    if not os.getenv("ADMIN_API_TOKEN", "").strip():
        raise RuntimeError("ADMIN_API_TOKEN must be configured in production.")

    if not os.getenv("CORS_ORIGINS", "").strip():
        raise RuntimeError("CORS_ORIGINS must be configured in production.")

    from backend.app.db.session import engine

    if engine.dialect.name != "postgresql":
        raise RuntimeError("Production DATABASE_URL must use PostgreSQL.")

    sslmode = engine.url.query.get("sslmode", "").lower()
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("Production PostgreSQL connections must require SSL.")


def require_admin(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv("ADMIN_API_TOKEN", "").strip()

    # Local development is intentionally open only when no admin token is set.
    if not token and app_environment() == "development":
        return

    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrative API is not configured.",
        )

    scheme, _, supplied_token = (authorization or "").partition(" ")
    if (
        scheme.lower() != "bearer"
        or not supplied_token
        or not hmac.compare_digest(supplied_token, token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid administrative bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
