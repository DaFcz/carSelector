"""Persists which car models a logged-in user has liked (see
`app/models/liked_model.py`). Anonymous likes never reach this module -
they live only in the page's `LikedModelsState` (`app/ui/state.py`) until
a login merges them in via `like_many`.

The liked ids feed the recommendation engine's soft ranking boost and the
catalog's default browse order (see `RecommendationEngine.recommend` and
`catalog.list_vehicles`'s `preferred_model_ids`).
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.liked_model import LikedModel


def list_ids(db: Session, user_id: int) -> set[int]:
    """Args:
        db: Session to read through.
        user_id: Whose likes to load.

    Returns:
        The ids of every `models` row the user has liked (empty if none).
    """
    return set(db.scalars(select(LikedModel.model_id).where(LikedModel.user_id == user_id)))


def like_many(db: Session, user_id: int, model_ids: Iterable[int]) -> None:
    """Likes each of `model_ids` for `user_id`. Idempotent: an already
    liked model is skipped, not duplicated (the table's unique constraint
    would reject it anyway).

    Args:
        db: Session to write through; committed here.
        user_id: Whose likes to add to.
        model_ids: Models to like.
    """
    wanted = set(model_ids) - list_ids(db, user_id)
    if not wanted:
        return
    now = datetime.now(UTC)
    db.add_all(LikedModel(user_id=user_id, model_id=model_id, created_at=now) for model_id in wanted)
    db.commit()


def like(db: Session, user_id: int, model_id: int) -> None:
    """Likes one model - see `like_many`.

    Args:
        db: Session to write through; committed here.
        user_id: Whose likes to add to.
        model_id: Model to like.
    """
    like_many(db, user_id, [model_id])


def unlike(db: Session, user_id: int, model_id: int) -> None:
    """Removes one like. No-op if the model wasn't liked.

    Args:
        db: Session to write through; committed here.
        user_id: Whose likes to remove from.
        model_id: Model to unlike.
    """
    db.execute(delete(LikedModel).where(LikedModel.user_id == user_id, LikedModel.model_id == model_id))
    db.commit()
