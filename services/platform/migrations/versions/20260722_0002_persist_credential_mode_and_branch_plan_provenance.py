"""persist credential mode and branch plan provenance

Revision ID: 20260722_0002
Revises: 20260713_0001
Create Date: 2026-07-22 03:14:16.978248
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "20260722_0002"
down_revision: str | None = "20260713_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A constant server_default lets Postgres backfill existing rows as part
    # of the ADD COLUMN itself (metadata-only, no table rewrite), so these
    # two can go straight to NOT NULL without a separate backfill pass.
    op.add_column(
        "analysis_runs",
        sa.Column(
            "credential_mode",
            sa.String(length=16),
            nullable=False,
            server_default="authenticated",
        ),
    )
    op.add_column(
        "analysis_runs",
        sa.Column(
            "credential_mode_transitions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
    )
    op.create_check_constraint(
        "ck_analysis_run_credential_mode",
        "analysis_runs",
        "credential_mode in ('authenticated', 'anonymous')",
    )

    # branches: add the new columns nullable first so existing rows can be
    # backfilled before the NOT NULL / CHECK / UNIQUE constraints that
    # depend on them are applied.
    op.add_column("branches", sa.Column("priority", sa.Integer(), nullable=True))
    op.add_column("branches", sa.Column("decision", sa.String(length=16), nullable=True))
    op.add_column(
        "branches", sa.Column("retrieval_time", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("branches", sa.Column("planner_version", sa.String(length=40), nullable=True))

    # Backfill decision from the boolean `included` column it replaces.
    op.execute(
        "UPDATE branches SET decision = CASE WHEN included THEN 'selected' ELSE 'excluded' END"
    )
    # Pre-existing branches predate branch-plan versioning; tag them as
    # 'legacy' rather than the current planner version so they don't
    # masquerade as output of a planner run that never produced them.
    op.execute("UPDATE branches SET planner_version = 'legacy'")
    # No historical retrieval timestamp exists; the closest proxy is the
    # parent analysis run's completion (falling back to its creation) time.
    op.execute(
        """
        UPDATE branches AS b
        SET retrieval_time = COALESCE(ar.completed_at, ar.created_at, now())
        FROM analysis_runs AS ar
        WHERE b.analysis_id = ar.id
        """
    )
    # `analysis_priority` was never unique, so rank rows into dense,
    # per-(analysis, repository) priorities that preserve relative order
    # instead of copying the raw values -- copying as-is could collide and
    # violate uq_branch_analysis_repo_planner_priority below.
    op.execute(
        """
        UPDATE branches AS b
        SET priority = ranked.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY analysis_id, repository_id
                ORDER BY analysis_priority, id
            ) - 1 AS rn
            FROM branches
        ) AS ranked
        WHERE b.id = ranked.id
        """
    )

    op.alter_column("branches", "priority", nullable=False)
    op.alter_column("branches", "decision", nullable=False, server_default="unevaluated")
    op.alter_column("branches", "planner_version", nullable=False)
    op.alter_column(
        "branches",
        "head_sha",
        existing_type=sa.VARCHAR(length=64),
        nullable=True,
    )

    op.drop_constraint("uq_branch_analysis_repo_name", "branches", type_="unique")
    op.create_index(op.f("ix_branches_repository_id"), "branches", ["repository_id"], unique=False)
    op.create_unique_constraint(
        "uq_branch_analysis_repo_planner_name",
        "branches",
        ["analysis_id", "repository_id", "planner_version", "name"],
    )
    op.create_unique_constraint(
        "uq_branch_analysis_repo_planner_priority",
        "branches",
        ["analysis_id", "repository_id", "planner_version", "priority"],
    )
    op.create_check_constraint(
        "ck_branch_decision",
        "branches",
        "decision in ('selected', 'excluded', 'unevaluated')",
    )
    op.create_check_constraint(
        "ck_branch_selection_reason_required",
        "branches",
        "decision = 'unevaluated' or selection_reason is not null",
    )
    op.create_check_constraint(
        "ck_branch_observed_fields_required",
        "branches",
        "decision = 'unevaluated' or (head_sha is not null and retrieval_time is not null)",
    )

    op.drop_column("branches", "included")
    op.drop_column("branches", "analysis_priority")


def downgrade() -> None:
    # Re-added nullable first (mirroring upgrade's approach) so rows written
    # under the new schema can be backfilled before NOT NULL is restored.
    op.add_column(
        "branches",
        sa.Column("analysis_priority", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "branches", sa.Column("included", sa.BOOLEAN(), autoincrement=False, nullable=True)
    )
    op.execute("UPDATE branches SET analysis_priority = priority")
    op.execute("UPDATE branches SET included = (decision = 'selected')")
    op.alter_column("branches", "analysis_priority", nullable=False)
    op.alter_column("branches", "included", nullable=False)

    op.drop_constraint("ck_branch_observed_fields_required", "branches", type_="check")
    op.drop_constraint("ck_branch_selection_reason_required", "branches", type_="check")
    op.drop_constraint("ck_branch_decision", "branches", type_="check")
    op.drop_constraint("uq_branch_analysis_repo_planner_priority", "branches", type_="unique")
    op.drop_constraint("uq_branch_analysis_repo_planner_name", "branches", type_="unique")
    op.drop_index(op.f("ix_branches_repository_id"), table_name="branches")

    # NOTE: this fails if any row has a NULL head_sha -- only possible for
    # data written after this migration's upgrade() ran, since the
    # pre-migration column was NOT NULL. Fix up or remove such rows first.
    op.alter_column(
        "branches",
        "head_sha",
        existing_type=sa.VARCHAR(length=64),
        nullable=False,
    )
    # NOTE: this also fails if two rows share (analysis_id, repository_id,
    # name) across different planner_versions -- possible once branch plans
    # have been re-run under the new schema. That data loss is inherent to
    # downgrading past a widened uniqueness scope; resolve duplicates first.
    op.create_unique_constraint(
        "uq_branch_analysis_repo_name",
        "branches",
        ["analysis_id", "repository_id", "name"],
        postgresql_nulls_not_distinct=False,
    )

    op.drop_column("branches", "planner_version")
    op.drop_column("branches", "retrieval_time")
    op.drop_column("branches", "decision")
    op.drop_column("branches", "priority")

    op.drop_constraint("ck_analysis_run_credential_mode", "analysis_runs", type_="check")
    op.drop_column("analysis_runs", "credential_mode_transitions")
    op.drop_column("analysis_runs", "credential_mode")
