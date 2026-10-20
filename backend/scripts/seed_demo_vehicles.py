"""Add the supplied car photo fleet to the local development database."""

import asyncio
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import select

# Run the script from a car-service directory while keeping this helper in a
# shared backend scripts folder.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "car-service"))

from app.core.database import get_sessionmaker
from app.models import Vehicle


DEMO_VEHICLES = [
    ("Tesla", "Roadster", "Red", 2024, "Premium", 2, "automatic", "electric", "DW-TES-001"),
    ("Mercedes-Benz", "G-Class", "Black", 2023, "SUV", 5, "automatic", "petrol", "DW-MBZ-002"),
    ("Mercedes-Benz", "C-Class", "Silver", 2024, "Sedan", 5, "automatic", "hybrid", "DW-MBZ-003"),
    ("Ford", "Mustang", "Blue", 2023, "Premium", 4, "automatic", "petrol", "DW-FRD-004"),
    ("Rolls-Royce", "Cullinan", "Black", 2024, "Premium", 5, "automatic", "petrol", "DW-RR-005"),
    ("Lamborghini", "Huracan", "Yellow", 2023, "Premium", 2, "automatic", "petrol", "DW-LAM-006"),
    ("Toyota", "Camry", "Silver", 2024, "Sedan", 5, "automatic", "hybrid", "DW-TOY-007"),
    ("Toyota", "RAV4", "White", 2024, "SUV", 5, "automatic", "hybrid", "DW-TOY-008"),
    ("BMW", "3 Series", "Graphite", 2024, "Premium", 5, "automatic", "petrol", "DW-BMW-009"),
    ("Jeep", "Wrangler", "Green", 2023, "SUV", 5, "automatic", "petrol", "DW-JEP-010"),
]


async def main() -> None:
    added = 0
    async with get_sessionmaker()() as session:
        for make, model, color, year, category, seats, transmission, fuel, plate in DEMO_VEHICLES:
            existing = await session.scalar(
                select(Vehicle).where(Vehicle.registration_number == plate)
            )
            if existing:
                continue
            session.add(
                Vehicle(
                    make=make,
                    model=model,
                    color=color,
                    year=year,
                    category=category,
                    seats=seats,
                    transmission=transmission,
                    fuel_type=fuel,
                    hourly_rate=Decimal("100.00"),
                    currency="USD",
                    registration_number=plate,
                    status="active",
                )
            )
            added += 1
        await session.commit()
    print(f"Added {added} demo vehicles; existing demo vehicles were left unchanged.")


if __name__ == "__main__":
    asyncio.run(main())
