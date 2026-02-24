from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import FeatureFlag


def is_enabled(db: Session, flag_name: str, default: bool = False) -> bool:
    flag = db.scalar(select(FeatureFlag).where(FeatureFlag.name == flag_name))
    if not flag:
        return default
    return bool(flag.enabled)
