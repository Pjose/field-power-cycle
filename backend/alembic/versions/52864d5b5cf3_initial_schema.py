"""initial schema

Revision ID: 52864d5b5cf3
Revises:
Create Date: 2026-09-04 07:30:02.934335

This migration is hand-corrected from what `alembic revision --autogenerate`
produced. Autogenerate emitted tables in an order that referenced foreign
keys before their target tables existed (`captures` -> `checklist_items`
before `checklist_items` was created, `checklist_items` -> `jobs` before
`jobs` was created, and similarly `jobs` <-> `technicians`) — this is a
genuine circular dependency in the schema (a job points at its assigned
technician; a technician points at their active job — same story for
captures and checklist items), and Postgres rejects a FOREIGN KEY
constraint against a table that doesn't exist yet. The fix: create every
table first with the circular columns present but unconstrained, then add
the two circular FK constraints afterward via ALTER TABLE, once both sides
of each cycle actually exist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '52864d5b5cf3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- tables with no circular dependencies first ---
    op.create_table('sites',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('client', sa.String(), nullable=False),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('geofence_radius_m', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('technicians',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('certifications', sa.JSON(), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('last_ping_at', sa.DateTime(), nullable=True),
        sa.Column('active_job_id', sa.String(), nullable=True),  # FK added below, after 'jobs' exists
        sa.Column('hourly_rate', sa.Float(), nullable=True),
        sa.Column('onboarding_steps', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('site_id', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('sla_tier', sa.String(), nullable=True),
        sa.Column('sla_deadline', sa.DateTime(), nullable=True),
        sa.Column('assigned_technician_id', sa.String(), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(), nullable=True),
        sa.Column('arrived_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id']),
        sa.ForeignKeyConstraint(['assigned_technician_id'], ['technicians.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('checklist_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('satisfied_by_capture_id', sa.String(), nullable=True),  # FK added below, after 'captures' exists
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('captures',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('technician_id', sa.String(), nullable=False),
        sa.Column('checklist_item_id', sa.String(), nullable=True),
        sa.Column('capture_type', sa.String(), nullable=True),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('capture_lat', sa.Float(), nullable=False),
        sa.Column('capture_lng', sa.Float(), nullable=False),
        sa.Column('capture_ts', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('checks', sa.JSON(), nullable=True),
        sa.Column('flag_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id']),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id']),
        sa.ForeignKeyConstraint(['checklist_item_id'], ['checklist_items.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- close the two genuine circular dependencies now that both sides exist ---
    op.create_foreign_key(
        'fk_technicians_active_job_id', 'technicians', 'jobs',
        ['active_job_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_checklist_items_satisfied_by_capture_id', 'checklist_items', 'captures',
        ['satisfied_by_capture_id'], ['id'],
    )

    # --- everything else has no circular dependency ---
    op.create_table('notification_rules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('trigger_event', sa.String(), nullable=False),
        sa.Column('recipient_role', sa.String(), nullable=False),
        sa.Column('channels', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('invoices',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('client', sa.String(), nullable=False),
        sa.Column('line_items', sa.JSON(), nullable=True),
        sa.Column('subtotal', sa.Float(), nullable=True),
        sa.Column('tax', sa.Float(), nullable=True),
        sa.Column('total', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('location_pings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('technician_id', sa.String(), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('accuracy_m', sa.Float(), nullable=True),
        sa.Column('device_ts', sa.DateTime(), nullable=True),
        sa.Column('received_ts', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('audit_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('actor', sa.String(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('ts', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('technician_id', sa.String(), nullable=True),
        sa.Column('client_name', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )


def downgrade() -> None:
    op.drop_table('users')
    op.drop_table('audit_events')
    op.drop_table('location_pings')
    op.drop_table('invoices')
    op.drop_table('notification_rules')

    op.drop_constraint('fk_checklist_items_satisfied_by_capture_id', 'checklist_items', type_='foreignkey')
    op.drop_constraint('fk_technicians_active_job_id', 'technicians', type_='foreignkey')

    op.drop_table('captures')
    op.drop_table('checklist_items')
    op.drop_table('jobs')
    op.drop_table('technicians')
    op.drop_table('sites')
