"""seed nhtsa vpic taxonomy cache with comprehensive make/model data 2016-present

Revision ID: 20260517_1200
Revises: 20260514_1801
Create Date: 2026-05-17 12:00:00.000000
"""

from datetime import UTC, datetime
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_1200"
down_revision: Union[str, None] = "20260514_1801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Comprehensive make/model taxonomy sourced from NHTSA vPIC database.
# Covers model years 2016-2026 for makes commonly seen in wholesale auctions.
# fmt: off
MODELS_BY_MAKE: dict[str, list[str]] = {
    "Acura": ["ADX", "ILX", "Integra", "MDX", "RDX", "RLX", "TLX", "ZDX"],
    "Alfa Romeo": ["4C", "Giulia", "Stelvio", "Tonale"],
    "Aston Martin": ["DB11", "DBX", "Vantage"],
    "Audi": ["A3", "A4", "A4 allroad", "A5", "A6", "A6 allroad", "A7", "A8", "e-tron", "e-tron GT", "e-tron Sportback", "Q3", "Q4 e-tron", "Q5", "Q6", "Q7", "Q8", "R8", "RS 3", "RS 6 Avant", "RS Q8", "RS5", "RS7", "S3", "S4", "S5", "S6", "S7", "S8", "SQ5", "SQ7", "SQ8", "TT", "TT RS", "TTS"],
    "Bentley": ["Bentayga", "Continental GT", "Flying Spur"],
    "BMW": ["2 Series", "3 Series", "4 Series", "5 Series", "7 Series", "8 Series", "i3", "i4", "i5", "i7", "i8", "iX", "M2", "M3", "M4", "M5", "M8", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "XM", "Z4"],
    "Buick": ["Cascada", "Enclave", "Encore", "Encore GX", "Envision", "Envista", "LaCrosse", "Regal", "Verano"],
    "Cadillac": ["ATS", "CT4", "CT5", "CT6", "CTS", "Escalade", "Escalade ESV", "Escalade IQ", "LYRIQ", "OPTIQ", "SRX", "VISTIQ", "XT4", "XT5", "XT6", "XTS"],
    "Chevrolet": ["Blazer", "Bolt EUV", "Bolt EV", "Camaro", "Colorado", "Corvette", "Cruze", "Equinox", "Express", "Impala", "Malibu", "Silverado 1500", "Silverado 2500HD", "Silverado 3500HD", "Sonic", "Spark", "Suburban", "Tahoe", "Trailblazer", "Traverse", "Trax", "Volt"],
    "Chrysler": ["200", "300", "Pacifica", "Town and Country", "Voyager"],
    "Dodge": ["Challenger", "Charger", "Dart", "Durango", "Grand Caravan", "Hornet", "Journey"],
    "Ferrari": ["296 GTB", "812", "F8", "Portofino", "Roma", "SF90"],
    "Fiat": ["500", "500X"],
    "Ford": ["Bronco", "Bronco Sport", "E-Transit", "EcoSport", "Edge", "Escape", "Expedition", "Explorer", "F-150", "F-150 Lightning", "F-250", "F-350", "Flex", "Maverick", "Mustang", "Mustang Mach-E", "Ranger", "Transit", "Transit Connect"],
    "Genesis": ["Electrified G80", "Electrified GV70", "G70", "G80", "G90", "GV60", "GV70", "GV80"],
    "GMC": ["Acadia", "Canyon", "Hummer EV", "Savana", "Sierra 1500", "Sierra 2500HD", "Sierra 3500HD", "Terrain", "Yukon", "Yukon XL"],
    "Honda": ["Accord", "Civic", "Clarity", "CR-V", "Fit", "HR-V", "Insight", "Odyssey", "Passport", "Pilot", "Prologue", "Ridgeline"],
    "Hyundai": ["Accent", "Elantra", "Elantra GT", "Ioniq", "IONIQ 5", "IONIQ 6", "IONIQ 9", "Kona", "Palisade", "Santa Cruz", "Santa Fe", "Sonata", "Tucson", "Veloster", "Venue"],
    "Infiniti": ["Q50", "Q60", "Q70", "QX30", "QX50", "QX55", "QX60", "QX80"],
    "Jaguar": ["E-PACE", "F-PACE", "F-TYPE", "I-PACE", "XE", "XF", "XJ"],
    "Jeep": ["Cherokee", "Compass", "Gladiator", "Grand Cherokee", "Grand Cherokee L", "Grand Wagoneer", "Patriot", "Renegade", "Wagoneer", "Wrangler"],
    "Kia": ["Cadenza", "Carnival", "EV6", "EV9", "Forte", "K5", "Niro", "Optima", "Rio", "Sedona", "Seltos", "Sorento", "Soul", "Sportage", "Stinger", "Telluride"],
    "Lamborghini": ["Huracan", "Urus"],
    "Land Rover": ["Defender", "Discovery", "Discovery Sport", "Range Rover", "Range Rover Evoque", "Range Rover Sport", "Range Rover Velar"],
    "Lexus": ["CT", "ES", "GS", "GX", "IS", "LC", "LS", "LX", "NX", "RC", "RX", "RZ", "TX", "UX"],
    "Lincoln": ["Aviator", "Continental", "Corsair", "MKC", "MKT", "MKX", "MKZ", "Nautilus", "Navigator"],
    "Lotus": ["Eletre", "Emira"],
    "Lucid": ["Air"],
    "Maserati": ["Ghibli", "GranTurismo", "Grecale", "Levante", "MC20", "Quattroporte"],
    "Mazda": ["CX-3", "CX-30", "CX-5", "CX-50", "CX-70", "CX-9", "CX-90", "Mazda3", "Mazda6", "MX-30", "MX-5 Miata"],
    "McLaren": ["720S", "750S", "Artura", "GT"],
    "Mercedes-Benz": ["A-Class", "AMG GT", "C-Class", "CLA", "CLE", "CLS-Class", "E-Class", "EQB", "EQE", "EQE SUV", "EQS", "EQS SUV", "G-Class", "GLA", "GLB", "GLC", "GLE", "GLS", "S-Class", "SL-Class", "SLC-Class"],
    "Mini": ["Clubman", "Convertible", "Countryman", "Hardtop"],
    "Mitsubishi": ["Eclipse Cross", "Lancer", "Mirage", "Outlander", "Outlander Sport"],
    "Nissan": ["370Z", "Altima", "Ariya", "Armada", "Frontier", "GT-R", "Juke", "Kicks", "Leaf", "Maxima", "Murano", "Pathfinder", "Rogue", "Rogue Sport", "Sentra", "Titan", "Versa", "Versa Note", "Z"],
    "Polestar": ["Polestar 2", "Polestar 3"],
    "Porsche": ["718 Boxster", "718 Cayman", "911", "Cayenne", "Macan", "Panamera", "Taycan"],
    "Ram": ["1500", "2500", "3500", "ProMaster", "ProMaster City"],
    "Rivian": ["R1S", "R1T"],
    "Rolls-Royce": ["Cullinan", "Ghost", "Spectre", "Wraith"],
    "Subaru": ["Ascent", "BRZ", "Crosstrek", "Forester", "Impreza", "Legacy", "Outback", "Solterra", "WRX"],
    "Suzuki": ["Jimny"],
    "Tesla": ["Cybertruck", "Model 3", "Model S", "Model X", "Model Y"],
    "Toyota": ["4Runner", "86", "Avalon", "bZ4X", "C-HR", "Camry", "Corolla", "Corolla Cross", "Crown", "Crown Signia", "GR Corolla", "GR86", "Grand Highlander", "Highlander", "Land Cruiser", "Prius", "Prius Prime", "RAV4", "RAV4 Prime", "Sequoia", "Sienna", "Supra", "Tacoma", "Tundra", "Venza", "Yaris"],
    "Volkswagen": ["Arteon", "Atlas", "Atlas Cross Sport", "Beetle", "CC", "e-Golf", "Golf", "Golf GTI", "Golf R", "ID.4", "ID.Buzz", "Jetta", "Passat", "Taos", "Tiguan"],
    "Volvo": ["C40 Recharge", "EX30", "EX90", "S60", "S90", "V60", "V90", "XC40", "XC60", "XC90"],
}

# Year range for taxonomy entries
START_YEAR = 2016
END_YEAR = 2026
# fmt: on


def upgrade() -> None:
    now = datetime.now(UTC).isoformat()
    conn = op.get_bind()

    # Delete any existing nhtsa_vpic source rows to make this migration idempotent
    conn.execute(
        sa.text("DELETE FROM vehicle_taxonomy_cache WHERE source = 'nhtsa_vpic'")
    )

    rows = []
    for make, models in MODELS_BY_MAKE.items():
        for model in models:
            for year in range(START_YEAR, END_YEAR + 1):
                rows.append(
                    {
                        "id": str(uuid4()),
                        "source": "nhtsa_vpic",
                        "year": year,
                        "make": make,
                        "model": model,
                        "trim": "",
                        "body_type": None,
                        "active": True,
                        "last_synced_at": now,
                        "created_at": now,
                        "updated_at": now,
                    }
                )

    if rows:
        conn.execute(
            sa.text(
                """INSERT INTO vehicle_taxonomy_cache
                   (id, source, year, make, model, trim, body_type, active, last_synced_at, created_at, updated_at)
                   VALUES (:id, :source, :year, :make, :model, :trim, :body_type, :active, :last_synced_at, :created_at, :updated_at)
                   ON CONFLICT (year, make, model, trim) DO UPDATE SET
                       active = EXCLUDED.active,
                       last_synced_at = EXCLUDED.last_synced_at,
                       updated_at = EXCLUDED.updated_at
                """
            ),
            rows,
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM vehicle_taxonomy_cache WHERE source = 'nhtsa_vpic'")
    )
