"""initial schema

Revision ID: c19b465c67fc
Revises: 
Create Date: 2026-09-30 09:46:42.371314
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c19b465c67fc'
down_revision = None
branch_labels = None
depends_on = None

# Enum types are created/dropped explicitly (create_type=False on the columns),
# because request_status is shared by three columns and must only be created once.
user_role = postgresql.ENUM("client", "operator", "admin", name="user_role", create_type=False)
episode_quality = postgresql.ENUM("good", "usable", "bad", name="episode_quality", create_type=False)
request_status = postgresql.ENUM(
    "submitted", "in_progress", "delivered", "accepted", "rejected",
    name="request_status", create_type=False,
)


def upgrade():
    bind = op.get_bind()
    user_role.create(bind)
    episode_quality.create(bind)
    request_status.create(bind)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('role', user_role, nullable=False),
    sa.Column('organisation', sa.String(length=200), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_users_email_lowercase')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('import_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('started_by', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('counts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('issues', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], name=op.f('fk_import_runs_started_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_runs'))
    )
    op.create_table('requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('task_name', sa.String(length=200), nullable=False),
    sa.Column('episodes_requested', sa.Integer(), nullable=False),
    sa.Column('deadline', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', request_status, server_default='submitted', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('episodes_requested > 0', name=op.f('ck_requests_episodes_requested_positive')),
    sa.ForeignKeyConstraint(['client_id'], ['users.id'], name=op.f('fk_requests_client_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_requests'))
    )
    op.create_index(op.f('ix_requests_client_id'), 'requests', ['client_id'], unique=False)
    op.create_index(op.f('ix_requests_status'), 'requests', ['status'], unique=False)
    op.create_table('episodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('episode_id', sa.String(length=50), nullable=False),
    sa.Column('robot_id', sa.String(length=50), nullable=False),
    sa.Column('task_name', sa.String(length=200), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_seconds', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('operator_name', sa.String(length=200), nullable=True),
    sa.Column('quality', episode_quality, nullable=False),
    sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('import_run_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('duration_seconds > 0', name=op.f('ck_episodes_duration_positive')),
    sa.ForeignKeyConstraint(['import_run_id'], ['import_runs.id'], name=op.f('fk_episodes_import_run_id_import_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_episodes')),
    sa.UniqueConstraint('episode_id', name=op.f('uq_episodes_episode_id'))
    )
    op.create_index('ix_episodes_good_recorded_at', 'episodes', ['recorded_at'], unique=False, postgresql_where=sa.text("quality = 'good'"))
    op.create_index('ix_episodes_recorded_at_robot_id', 'episodes', ['recorded_at', 'robot_id'], unique=False)
    op.create_index('ix_episodes_task_name_quality', 'episodes', ['task_name', 'quality'], unique=False)
    op.create_table('request_status_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('from_status', request_status, nullable=True),
    sa.Column('to_status', request_status, nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_request_status_events_actor_id_users')),
    sa.ForeignKeyConstraint(['request_id'], ['requests.id'], name=op.f('fk_request_status_events_request_id_requests')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_request_status_events'))
    )
    op.create_index(op.f('ix_request_status_events_request_id'), 'request_status_events', ['request_id'], unique=False)
    op.create_table('assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('episode_id', sa.Integer(), nullable=False),
    sa.Column('assigned_by', sa.Integer(), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], name=op.f('fk_assignments_assigned_by_users')),
    sa.ForeignKeyConstraint(['episode_id'], ['episodes.id'], name=op.f('fk_assignments_episode_id_episodes')),
    sa.ForeignKeyConstraint(['request_id'], ['requests.id'], name=op.f('fk_assignments_request_id_requests')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignments')),
    sa.UniqueConstraint('episode_id', name=op.f('uq_assignments_episode_id'))
    )
    op.create_index(op.f('ix_assignments_request_id'), 'assignments', ['request_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_assignments_request_id'), table_name='assignments')
    op.drop_table('assignments')
    op.drop_index(op.f('ix_request_status_events_request_id'), table_name='request_status_events')
    op.drop_table('request_status_events')
    op.drop_index('ix_episodes_task_name_quality', table_name='episodes')
    op.drop_index('ix_episodes_recorded_at_robot_id', table_name='episodes')
    op.drop_index('ix_episodes_good_recorded_at', table_name='episodes', postgresql_where=sa.text("quality = 'good'"))
    op.drop_table('episodes')
    op.drop_index(op.f('ix_requests_status'), table_name='requests')
    op.drop_index(op.f('ix_requests_client_id'), table_name='requests')
    op.drop_table('requests')
    op.drop_table('import_runs')
    op.drop_table('users')

    bind = op.get_bind()
    request_status.drop(bind)
    episode_quality.drop(bind)
    user_role.drop(bind)
