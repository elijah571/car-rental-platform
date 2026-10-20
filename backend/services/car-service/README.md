# Car Rental Car Service

Vehicle inventory and catalog API for the Car Rental Platform.

## Development

Install the service dependencies and start it from this directory:

```bash
uv sync --locked
uv run --locked uvicorn app.main:app --reload --port 8002
```

Configure `DATABASE_URL` or `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in the repository environment, then apply this service's migrations:

```bash
uv run --locked alembic upgrade head
```

The API runs at <http://127.0.0.1:8002>; interactive docs are at <http://127.0.0.1:8002/docs>. `/health` reports liveness and `/ready` checks the database and vehicle schema.

Set the shared `JWT_SECRET` used by auth-service. Vehicle writes require a valid local access token with the `platform-admin` role. The public catalog exposes active vehicles only.

## Vehicle API

- `POST /vehicles` creates an inventory record.
- `GET /vehicles` lists active vehicles by default. Filter with `make`, `model`, `category`, `min_seats`, `max_hourly_rate`, and `status`; paginate with `limit` and `offset`.
- `GET /vehicles/{vehicle_id}` retrieves one vehicle.
- `PATCH /vehicles/{vehicle_id}` updates vehicle details or status.
- `DELETE /vehicles/{vehicle_id}` retires a vehicle without deleting its history.

Vehicles include a color snapshot field used by bookings and rental tickets. Existing records receive `unspecified` when migrated; supply a color for newly created vehicles.

Administrators set each vehicle’s `hourly_rate` when creating or editing inventory; prices are independent per vehicle and displayed as USD per hour. Creation and update requests validate vehicle properties and normalize registration numbers to uppercase. Registration numbers must be unique.

