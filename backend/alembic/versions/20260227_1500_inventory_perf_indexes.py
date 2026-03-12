"""Inventory performance indexes for Postgres

Revision ID: 20260227_1500
Revises: 20260218_0600
Create Date: 2026-02-27 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260227_1500"
down_revision: Union[str, None] = "20260218_0600"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Composite scan path for default inventory queries.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_available_updated_at "
        "ON vehicles (available, updated_at DESC, vin)"
    )

    # Functional indexes preserve current lower(...) query semantics without refactoring routes.
    op.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_lower_make ON vehicles ((lower(make)))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_lower_model ON vehicles ((lower(model)))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_lower_trim ON vehicles ((lower(coalesce(trim, ''))))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vehicles_lower_body_type ON vehicles ((lower(coalesce(body_type, ''))))")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_lower_source_type ON vehicles ((lower(coalesce(source_type, ''))))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_lower_location_state ON vehicles ((lower(coalesce(location_state, ''))))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_lower_drivetrain ON vehicles ((lower(coalesce(drivetrain, ''))))"
    )

    # Expression indexes for JSON-backed facets/filters used in API routes.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_dom_expr "
        "ON vehicles ((((features_normalized ->> 'days_on_market')::int)))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_exterior_color_expr "
        "ON vehicles ((lower(coalesce(features_normalized ->> 'exterior_color', ''))))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_interior_color_expr "
        "ON vehicles ((lower(coalesce(features_normalized ->> 'interior_color', ''))))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_fuel_type_expr "
        "ON vehicles ((lower(coalesce(features_normalized ->> 'fuel_type', ''))))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_transmission_expr "
        "ON vehicles ((lower(coalesce(features_normalized ->> 'transmission', ''))))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_inventory_type_expr "
        "ON vehicles ((lower(coalesce(features_normalized ->> 'inventory_type', ''))))"
    )

    # Fast path for "has_images=true" filters in inventory read routes.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicles_has_images_partial "
        "ON vehicles (vin) WHERE available IS TRUE AND coalesce(json_array_length(images), 0) > 0"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS idx_vehicles_has_images_partial")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_inventory_type_expr")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_transmission_expr")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_fuel_type_expr")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_interior_color_expr")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_exterior_color_expr")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_dom_expr")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_drivetrain")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_location_state")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_source_type")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_body_type")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_trim")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_model")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_lower_make")
    op.execute("DROP INDEX IF EXISTS idx_vehicles_available_updated_at")
