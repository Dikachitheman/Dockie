"""add reference_ports with PostGIS spatial queries

Revision ID: a7b3c9d2e4f6
Revises: 5d6dfe7c9a21
Create Date: 2026-03-31 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import geoalchemy2
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7b3c9d2e4f6"
down_revision = "5d6dfe7c9a21"
branch_labels = None
depends_on = None


# West African corridor ports + key US load ports
SEED_PORTS = [
    # Nigeria
    ("NGLAG", "Lagos (Apapa)", "Nigeria", 6.4478, 3.3903, 5.0),
    ("NGAPP", "Apapa Terminal", "Nigeria", 6.4400, 3.3800, 5.0),
    ("NGTIN", "Tin Can Island", "Nigeria", 6.4300, 3.3500, 5.0),
    ("NGLOS", "Lagos (Onne)", "Nigeria", 4.7100, 7.1500, 5.0),
    ("NGPHC", "Port Harcourt", "Nigeria", 4.7700, 7.0100, 5.0),
    # Ghana
    ("GHTEM", "Tema", "Ghana", 5.6300, -0.0100, 5.0),
    ("GHTKD", "Takoradi", "Ghana", 4.8800, -1.7500, 5.0),
    # Togo
    ("TGLFW", "Lome", "Togo", 6.1300, 1.2800, 5.0),
    # Benin
    ("BJCOO", "Cotonou", "Benin", 6.3500, 2.4300, 5.0),
    # Cote d'Ivoire
    ("CIABJ", "Abidjan", "Cote d'Ivoire", 5.2800, -3.9900, 5.0),
    # Senegal
    ("SNDKR", "Dakar", "Senegal", 14.6900, -17.4400, 5.0),
    # Cameroon
    ("CMDLA", "Douala", "Cameroon", 4.0500, 9.7000, 5.0),
    # US load ports
    ("USBAL", "Baltimore", "United States", 39.2700, -76.5800, 3.0),
    ("USSAV", "Savannah", "United States", 32.0800, -81.0900, 3.0),
    ("USJAX", "Jacksonville", "United States", 30.3300, -81.6600, 3.0),
    ("USHOU", "Houston", "United States", 29.7600, -95.3700, 3.0),
    ("USNWK", "Newark", "United States", 40.6800, -74.1500, 3.0),
    # Transshipment / waypoint ports
    ("ESVLC", "Valencia", "Spain", 39.4500, -0.3200, 3.0),
    ("ESALG", "Algeciras", "Spain", 36.1300, -5.4400, 3.0),
    ("MAPTM", "Tanger Med", "Morocco", 35.8900, -5.5100, 3.0),
    ("CVMIN", "Mindelo", "Cape Verde", 16.8900, -24.9900, 3.0),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "reference_ports",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("locode", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"
            ),
            nullable=False,
        ),
        sa.Column("port_type", sa.String(length=64), nullable=False, server_default="seaport"),
        sa.Column("geofence_radius_nm", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("locode"),
    )
    op.create_index(
        "ix_reference_ports_geom",
        "reference_ports",
        ["geom"],
        postgresql_using="gist",
    )

    # Seed reference ports
    import uuid

    for locode, name, country, lat, lon, radius in SEED_PORTS:
        port_id = str(uuid.uuid4())
        op.execute(
            sa.text(
                "INSERT INTO reference_ports (id, locode, name, country, latitude, longitude, geom, port_type, geofence_radius_nm) "
                "VALUES (:id, :locode, :name, :country, :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 'seaport', :radius)"
            ).bindparams(
                id=port_id, locode=locode, name=name, country=country,
                lat=lat, lon=lon, radius=radius,
            )
        )

    # Add spatial indexes on existing position tables (GiST)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_positions_geom ON positions USING gist (geom)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_latest_positions_geom ON latest_positions USING gist (geom)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_latest_positions_geom")
    op.execute("DROP INDEX IF EXISTS ix_positions_geom")
    op.drop_index("ix_reference_ports_geom", table_name="reference_ports")
    op.drop_table("reference_ports")
