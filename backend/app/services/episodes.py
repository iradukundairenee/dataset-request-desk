"""Episode browsing for operators (filters + pagination)."""
from sqlalchemy import func, select

from app.models import Assignment, Episode
from app.services.normalise import normalise_task_name


def list_episodes(db, task_name=None, quality=None, robot_id=None, unassigned_only=False, limit=50, offset=0):
    """Returns (episodes, total). Each episode gets `assigned_request_id` (None if free)."""
    query = select(Episode, Assignment.request_id).outerjoin(Assignment, Assignment.episode_id == Episode.id)
    if task_name:
        # Same normalisation as the importer, so "Pick  Cup" finds "pick cup".
        query = query.where(Episode.task_name == normalise_task_name(task_name))
    if quality is not None:
        query = query.where(Episode.quality == quality)
    if robot_id:
        query = query.where(Episode.robot_id == robot_id.strip().lower())
    if unassigned_only:
        query = query.where(Assignment.id.is_(None))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(Episode.recorded_at.desc(), Episode.id.desc()).limit(limit).offset(offset)).all()

    episodes = []
    for episode, request_id in rows:
        episode.assigned_request_id = request_id
        episodes.append(episode)
    return episodes, total


def list_task_names(db):
    """Distinct task names across all episodes, for the request form's suggestions."""
    return db.scalars(select(Episode.task_name).distinct().order_by(Episode.task_name)).all()
