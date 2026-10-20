Car Rental Platform --- Project Specification and Development Record
Document type: Project specification, architecture overview, and
implementation log
Project status: Local development platform with a React/TypeScript frontend
and six running backend services. Customer fleet browsing, availability search,
registration/sign-in UI, server-priced booking holds, Stripe payment UI, and
receipt display are connected to the APIs. Operations vehicle inventory screens
are connected to car-service. Verified payment confirmation, receipt snapshots,
rental status transitions, and durable notification delivery are implemented.
External Cognito, Stripe webhook, and SES credentials and AWS deployment
remain unconfigured.
Last updated: 20 October 2026
Repository: /home/elijah/projects/car-rental-platform
Purpose of this document: Capture the agreed product requirements,
architecture, technical decisions, development standards, current
implementation status, and unresolved decisions in one place. Update
this document when requirements or implementation decisions change.

1. Project Overview
   The Car Rental Platform is a full-stack system for renting cars for a
   selected period. Customers should be able to discover available cars,
   view pricing, book a car, pay securely, and receive a receipt or rental
   ticket. Administrators manage the vehicle inventory and bookings.

The system is intended to be built with production standards from the
beginning: secure identity handling, reliable payments, prevention of
overlapping bookings, auditable state transitions, automated tests,
migrations, containerized development, and a clear path to AWS
deployment.
1.1 Main user types

- Customer: Registers and verifies an account, signs in, browses
  cars, checks prices and availability, books a rental, pays, and
  receives a receipt/ticket.
- Platform administrator: Creates, reads, updates, archives or
  deletes cars according to the final retention policy; manages
  bookings; and initially has exclusive authority to cancel bookings.
- Authorized return inspector / operational staff: The business
  rules require an authorized return inspection before a returned car
  becomes available again. The exact staff role and permission model
  still need to be defined.
  The final role names, permission matrix, and whether there are
  additional operational roles remain to be specified.

2. Product Requirements
   2.1 Customer journey
1. A customer registers or signs in.
1. The identity provider handles email verification and supported
   account recovery flows.
1. The customer browses cars and sees relevant vehicle details,
   availability, and rental pricing.
1. The customer selects a rental start and end time.
1. The backend validates the requested period and computes the price.
1. A booking is created and held for up to 15 minutes while payment is
   pending.
1. The customer pays through Stripe.
1. The backend accepts payment success only after validating a Stripe
   webhook; it must not trust a browser redirect as proof of payment.
1. The customer receives a receipt or rental ticket showing the rental
   period and the booked vehicle's make, model, color, and license
   plate.
1. After the rental ends, the car remains unavailable until an
   authorized return inspection has been completed.
   2.2 Vehicle inventory
   Administrators need to be able to:

- Create a vehicle.
- Fetch/list vehicles.
- Update vehicle details.
- Archive or delete vehicles, subject to a final policy that protects
  historical bookings and financial records.
- Manage availability and booking-related operational state.
  Customers need to be able to browse vehicles, see pricing, and discover
  availability for a requested period.

Vehicle attributes explicitly identified so far include:

- Make
- Model
- Color
- License plate
- Rental price
  Other fields such as year, class/category, description, images, mileage,
  location, and maintenance status may be useful, but have not yet been
  finalized as requirements.
  2.3 Pricing and currency
- Each vehicle has its own administrator-managed hourly rate. New vehicle forms
  may default to USD $25 per hour, and admins can set or update the rate per car.
- Customers choose rental duration in the checkout cart, up to seven days.
- Charge proportionally to the actual duration of the selected rental
  period.
- Currency: USD only for the initial version.
- Round the calculated amount to the nearest cent using a documented,
  consistent rounding rule.
- The server calculates and validates the price. A client-supplied
  total must never be trusted.
- The exact handling of seconds, minimum billable duration,
  invalid/reversed periods, and timezone normalization must be
  specified in the pricing implementation and tests.
  A basic pricing expression is:

amount = rental_duration_in_hours × 100 USD

The production implementation should use exact decimal or
integer-minor-unit arithmetic rather than binary floating-point for
money.
2.4 Booking and availability rules

- A pending unpaid booking has a 15-minute hold.
- The system must prevent overlapping confirmed or otherwise blocking
  bookings for the same car.
- Overlap checks must be safe under concurrent requests.
  Application-level checks alone are not enough; use PostgreSQL
  transactions and an appropriate database constraint or locking
  strategy.
- A car is not available for another rental merely because the
  booked rental period has ended.
- It becomes available only after the rental period has ended and
  an authorized return inspection has been completed.
- Initially, only administrators may cancel bookings.
- Rental pickup, return, and return inspection transitions are currently
  available to `platform-admin`. This is a provisional permission choice
  until the operational role matrix is decided. A booking remains blocking
  until its scheduled end and approved return inspection.
- Expiration of an unpaid hold runs in a booking-service background task
  and updates expired holds idempotently. Multi-replica scheduling and
  operational monitoring remain to be implemented.
- Historical bookings and receipts must preserve the vehicle and price
  details that applied at booking time, even if the vehicle record
  changes later.
  The precise rules for early return, late return, no-show, inspection
  failure, damage, maintenance holds, and cancellation after payment
  remain open product decisions.
  2.5 Payment and receipt requirements
- Use Stripe for payment processing.
- Verify webhook signatures before processing Stripe events.
- Treat verified webhook events---not the frontend success page---as
  the authoritative signal for payment status.
- Handle duplicate webhook delivery idempotently.
- Store payment and booking state in PostgreSQL.
- Preserve enough event/payment identifiers to reconcile internal
  records with Stripe.
- Issue a receipt or rental ticket with the rental start/end and a
  snapshot of vehicle make, model, color, and plate.
- Do not store raw card details.
- Refund policy and the precise payment-failure/retry behavior have
  not yet been finalized.

3. Identity, Authentication, and Authorization
   3.1 Identity provider
   Use Amazon Cognito for user identity and the supported identity
   lifecycle, including:

- Registration/sign-up
- Email verification
- Login
- Password recovery
  The platform will not build a parallel password-management system unless
  a future requirement explicitly changes this decision.
  3.2 API authentication
  FastAPI services must validate Cognito access tokens correctly.
  Validation must include the appropriate checks for:
- Cryptographic signature using the issuer's published keys.
- Issuer.
- Expiration and relevant time claims.
- Expected token use and audience/client identifier, according to the
  chosen Cognito token type and app-client configuration.
- Required scopes or claims where applicable.
  Do not merely decode a JWT and treat its contents as trusted.
  Authorization decisions must be made by the backend.
  3.3 Authorization
- Enforce role- and permission-based authorization on the server.
- Do not trust role values, user IDs, prices, or permissions supplied
  by the client without server-side verification.
- Define a permission matrix for customer, administrator, and
  return-inspection operations before implementing protected business
  endpoints.
- Keep authentication (who the user is) distinct from authorization
  (what the user may do).

4. Target Architecture
   The intended repository is a service-oriented monorepo. Each service
   owns a clear business responsibility and its relevant application logic.
   Shared packages should contain stable contracts and reusable testing
   support rather than turning into a shared database-model layer that
   tightly couples all services.
   4.1 Planned services
   Service Responsibility Status
   auth-service Cognito token Initial implementation; full validation
   integration and
   application
   identity/authorization
   boundaries

car-service Vehicle inventory, Initial implementation
details, administration,
and availability-related
vehicle state

booking-service Booking lifecycle, time Initial implementation
windows, holds, overlap
prevention,
cancellation,
return/inspection state

payment-service Stripe checkout/payment Initial implementation
integration, webhook
verification, payment
state, reconciliation

receipt-service Receipt/rental-ticket Initial implementation
generation and
historical snapshots

notification-service Email and other Initial implementation
booking/payment
notifications
These are planned boundaries, not a claim that every service must
immediately be deployed independently. The final deployment and
service-communication strategy should be justified by operational needs.
4.2 Technology choices
Area Intended technology
Language Python 3.12+
HTTP API FastAPI
Data validation/settings Pydantic and Pydantic Settings
ORM SQLAlchemy 2.x
Database migrations Alembic
Primary database PostgreSQL
Cache / rate limiting / short-lived coordination Redis
Identity Amazon Cognito
Payment processing Stripe
AWS SDK boto3
Containers Docker and Docker Compose
Python project/dependency management uv
Testing pytest and FastAPI test client
GitHub Actions service tests, PostgreSQL migrations, and Alembic checks
AWS edge/API API Gateway
Event delivery SQS and EventBridge
Event-driven/scheduled execution Lambda
Infrastructure as code Terraform (planned)
4.3 Hybrid AWS deployment
The deployment direction is a hybrid model:

- Containerized FastAPI services for long-running API workloads where
  appropriate.
- API Gateway as the public API entry point.
- Lambda for appropriate event-driven and scheduled tasks.
- SQS for durable asynchronous work and retryable message processing.
- EventBridge for event routing and scheduled triggers.
- PostgreSQL as the system of record.
- Redis for caching, rate limiting, and short-lived coordination---not
  as the authoritative source for bookings, payments, or receipts.
  The exact AWS hosting choice for containers, networking, environments,
  secrets, and database hosting must be documented when infrastructure
  design begins. DynamoDB should be introduced only where a specific
  requirement justifies it; it is not a default replacement for
  PostgreSQL.

5. Data Ownership and Reliability
   5.1 System of record
   PostgreSQL is the source of truth for:

- Vehicles and their durable state.
- Bookings and booking status transitions.
- Payments and payment status.
- Receipts and historical booking/vehicle/pricing snapshots.
- Relevant audit and idempotency records.
  Redis may cache derived data, apply rate limits, or coordinate
  short-lived work, but a Redis cache miss or restart must not destroy the
  authoritative business state.
  5.2 Database and concurrency
- Use SQLAlchemy 2.x models and Alembic migrations.
- Treat migrations as versioned, reviewed code.
- Avoid modifying an already-applied production migration to change
  its historical meaning; add a new migration instead.
- Prevent overlapping reservations using database-level concurrency
  protection, not just a "check then insert" application sequence.
- Use transactions for state changes that must be atomic.
- Keep monetary values precise.
- Preserve snapshots needed for historical receipts.
- Add appropriate indexes, foreign keys, uniqueness rules, check
  constraints, and deletion policies as the domain model is designed.
  5.3 Events and background work
  SQS/EventBridge/Lambda consumers and scheduled jobs should be
  idempotent. A repeated event must not double-charge a customer, create
  duplicate receipts, or apply a booking transition twice.

Where a database update must reliably result in an event being
published, use a transactional outbox or another explicitly designed
reliable-publishing pattern. Avoid assuming a database commit and a
network publish can form one atomic operation.

The exact event schemas, retry policies, dead-letter queues, event
versioning, and reconciliation procedures remain to be designed. 6. Security and Production Standards
Security is part of the implementation baseline, not a final cleanup
phase.
6.1 Secrets and configuration

- Do not commit .env files or credentials.
- Commit only safe placeholders in .env.example.
- Use environment configuration locally and an appropriate managed
  secret mechanism in deployment.
- Never print, log, or include credentials in project documentation.
- Validate required configuration at application startup.
- Keep development and production settings separated.
  6.2 API security
  Plan and test for:
- Cognito JWT signature and claims validation.
- Server-side role/permission enforcement.
- Request schema validation and safe error responses.
- Rate limiting at suitable boundaries.
- SQL injection prevention through parameterized ORM/query usage.
- XSS prevention where user-controlled content is rendered by a
  frontend or included in documents.
- CSRF protections where browser cookie-based authentication is used.
- CORS restrictions appropriate to each environment.
- Secure transport and appropriate security headers.
- File upload validation if uploads are added.
- Internal API authentication and trust boundaries.
- Least-privilege AWS IAM roles and service permissions.
- Safe handling of personally identifiable information.
- Auditability for administrative actions and sensitive state changes.
  6.3 Payments
- Verify Stripe webhook signatures.
- Use idempotency keys/records where needed.
- Reconcile internal payment state with Stripe.
- Do not treat unverified client requests as proof of payment.
- Do not store card numbers or security codes.
  6.4 Observability and operations
  Production readiness should include structured logs, correlation/request
  IDs, metrics, useful health/readiness checks, error reporting, database
  backups, restore testing, monitoring and alerting, and documented
  operational runbooks. Do not expose secrets or sensitive customer data
  in logs.

7. Repository Layout
   The repository separates the deployable browser application from the
   service-oriented Python backend:
   car-rental-platform/
   ├── frontend/
   │ ├── public/cars/              # vehicle imagery used by the UI
   │ ├── src/                      # React and TypeScript application
   │ ├── package.json
   │ └── vite.config.ts
   ├── backend/
   │ ├── services/
   │ │ ├── auth-service/
   │ │ ├── car-service/
   │ │ ├── booking-service/
   │ │ ├── payment-service/
   │ │ ├── receipt-service/
   │ │ └── notification-service/
   │ └── shared/platform-security/
   ├── infrastructure/
   ├── scripts/
   ├── car_rental_ui_design.pdf
   ├── .env.example
   ├── compose.yaml
   └── README.md
   Compose remains at the repository root and builds from `backend/`.
   The Vite application runs independently and uses a local proxy to call
   the public auth, car, and booking API routes.
8. Local Development Environment
   8.1 Known environment
   The current development machine is running Ubuntu 24.04 LTS. The project
   uses Python 3.12, uv, Git, Docker, and Docker Compose.

Project directory:

/home/elijah/projects/car-rental-platform
8.2 Local services
The root compose.yaml currently defines PostgreSQL and Redis for local
development:

- PostgreSQL 16, published only on 127.0.0.1:5433.
- Redis 7, published only on 127.0.0.1:6380.
- Separate persistent Docker volumes for PostgreSQL and Redis.
- Health checks for both services.
  These non-default host ports were chosen to avoid conflicts with other
  local projects and services. Do not change them without checking for
  conflicts and updating configuration consistently.

The local PostgreSQL database has been verified as:

- Database: car_rental
- Database user: car_rental_dev
- PostgreSQL version observed: 16.14
  Redis responded successfully to PING. Service-specific Alembic
  migrations have since created domain tables in PostgreSQL.
  8.3 Environment variables
  The root .env contains local configuration, including PostgreSQL
  settings and existing ImageKit settings. Its secret values must remain
  private and must not be copied into this document or committed to Git.

The auth-service currently builds its asynchronous database URL using
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST,
and POSTGRES_PORT. Verify .env loading from both the service working
directory and the eventual container runtime before relying on it in
deployment. 9. Current Implementation Status
This section records the state known at the time of writing. Update it
as implementation progresses.
9.1 Completed

- [x] Initial monorepo structure started.
- [x] Root Docker Compose configuration created for PostgreSQL and
      Redis.
- [x] PostgreSQL container started and healthy.
- [x] Redis container started and healthy.
- [x] Auth-service Python project initialized and managed with uv.
- [x] FastAPI application created.
- [x] Root endpoint implemented.
- [x] Health endpoint implemented.
- [x] SQLAlchemy asynchronous engine and session factory configured.
- [x] Live asynchronous PostgreSQL connection tested successfully.
- [x] Alembic configuration and asynchronous migration environment
      created.
- [x] pytest test dependencies installed.
- [x] Two FastAPI endpoint tests written and passing.
- [x] Testing client deprecation warning resolved after adding
      httpx2 as a development dependency.
- [x] alembic check ran against PostgreSQL without raising an error.
- [x] Initial car, booking, payment, notification, and receipt service
      implementations and database migrations created.
- [x] Receipt service stores idempotent USD rental receipt snapshots;
      local migration applied and health/readiness endpoints verified.
- [x] Shared Cognito access-token validation checks signature, issuer,
      expiry, token use, and app-client ID for car and booking APIs.
- [x] Vehicle management writes require the `platform-admin` Cognito
      group; booking ownership comes from the authenticated Cognito subject.
- [x] Booking prices are calculated server-side at USD 100/hour using
      Decimal arithmetic and half-up cent rounding. Bookings snapshot
      vehicle details, reserve a 15-minute hold, and enforce time overlap
      in PostgreSQL.
- [x] Verified Stripe success events validate the recorded amount and
      currency, then commit an idempotent payment-delivery outbox event in
      PostgreSQL before acknowledging Stripe.
- [x] A leased payment worker confirms bookings, creates receipts, and queues
      receipt email using idempotent service requests. Transient failures use
      exponential retry; events stop after 20 failed attempts and can be
      inspected or requeued through payment-service internal routes.
- [x] If Stripe reports a successful charge after a booking cannot be
      confirmed, payment-service stores `succeeded_unapplied` and
      acknowledges the event for manual reconciliation.
- [x] The payment outbox worker creates an idempotent receipt snapshot from
      the confirmed booking's saved vehicle and rental details. Delivery
      continues independently of Stripe's webhook retry window.
- [x] Customers can query active vehicle availability for a timezone-aware
      rental window; blocking bookings are excluded and the response
      includes the server-calculated rental total.
- [x] Customers can start checkout only for their own pending booking.
      Payment intent input contains a booking ID only; the payment service
      reads the authoritative amount and currency from the booking service.
      A database constraint permits one payment record per booking.
- [x] Booking status transitions cover paid confirmation, rental start,
      return, inspection failure, reinspection, and completion, with status
      audit records. Vehicles remain blocked through inspection and until
      the scheduled rental end.
- [x] Verified payments look up the active customer's verified email and
      queue an idempotent receipt message. A PostgreSQL worker retries email
      delivery with leases and exponential backoff.
- [x] Customers can retrieve their receipt through the booking service.
      Cognito ownership (or platform-admin membership) is checked before the
      booking service uses its service key to fetch the receipt.
- [x] Root Compose builds and runs all six APIs, PostgreSQL, and Redis.
      All six `/ready` endpoints reported a connected database after the
      latest booking/payment rebuild.
- [x] Focused auth (9), booking/security/availability (12), payment (8),
      notification retry (1), car inventory API (2), receipt API (2), and
      shared Cognito validation (4) tests pass. Payment tests cover Stripe
      amount mismatch, durable downstream failure retry, duplicate-event
      idempotency, unapplied charges, and failed-job recovery.
- [x] Cross-service payment delivery no longer depends on Stripe retries:
      payment-service stores webhook success in an outbox before responding
      and retries booking, receipt, and email-queue delivery itself. The
      notification service has its own persistent delivery queue.
- [x] GitHub Actions runs locked dependency installation, PostgreSQL
      migrations, migration drift checks, and focused tests per service.
- [ ] Automated reconciliation/refunds for `succeeded_unapplied` payments
      depend on the unresolved refund policy.
9.2 Current application endpoints
Customer-facing core endpoints:

- `POST /auth/register`, `/auth/confirm`, `/auth/login`, `/auth/refresh`,
  and `/auth/logout` for Cognito account flows.
- `GET /vehicles` and `GET /vehicles/{vehicle_id}` for the public active
  vehicle catalog; vehicle writes require a platform administrator.
- `GET /bookings/availability`, `POST /bookings`, customer-owned booking
  reads, `GET /bookings/{booking_id}/receipt`, and
  `POST /bookings/{booking_id}/payment-intent`.
- Admin rental operations: `/bookings/{booking_id}/start`, `/return`, and
  `/inspection`.
- `POST /payments/webhooks/stripe` for verified Stripe delivery.
- Internal payment recovery routes, protected by the payment service key:
  `GET /payments/internal/delivery-outbox/failed` and
  `POST /payments/internal/delivery-outbox/{event_id}/retry`.
- Internal receipt creation and notification enqueue endpoints use their
  service API keys. Each service also exposes `/health`, `/ready`, and
  `/docs`.
Each service exposes `/health` and `/ready`; the latter checks its
database. These endpoints do not provide full production observability.
9.3 Current test baseline
Focused auth tests passed (9 tests), booking/security/availability/lifecycle
tests passed (12 tests), car inventory API tests passed (2), payment schema,
durable outbox, retry, idempotency, and recovery tests passed (8), receipt
API tests passed (2), notification retry scheduling passed (1), and shared
Cognito validation tests passed (4): 38 tests total. A disposable payment
record was delivered by the running
outbox worker through the local booking, receipt, auth-contact, and
notification APIs; it created one booking transition, receipt, and queued
email, then the temporary rows were removed. End-to-end Cognito checkout,
live Stripe signature validation, SES delivery, and lifecycle API/database
tests remain.
9.4 Alembic status and known issue

- Each implemented service has its own asynchronous Alembic environment,
  initial migration, and service-specific version table.
- Initial and follow-up migrations for auth, booking, car, payment,
  notification, and receipt tables have been applied to local PostgreSQL.
- Alembic logging was duplicated because the named Alembic logger also
  propagated to the root logger, which had the same console handler.
  All service alembic.ini files now disable propagation for that logger.
  9.5 Dependencies requiring review
  The current project dependencies include FastAPI, SQLAlchemy, Alembic,
  asyncpg, Pydantic Settings, Uvicorn, and additional packages such as
  fastapi-users[sqlalchemy], aiosqlite, python-dotenv, and
  imagekitio.

Because Cognito is the intended identity provider, review whether
fastapi-users[sqlalchemy] is necessary before building
application-managed authentication. Similarly, confirm whether SQLite
and ImageKit dependencies are actually required by the intended
features. Do not remove dependencies until their use and purpose have
been checked. 10. Development Workflow
Work incrementally, verify each step, and do not move on until the
current step is understood and validated.

1. Confirm and document the architecture and development baseline.
2. Finish the Alembic setup and investigate duplicated logging.
3. Define the first domain models and their ownership.
4. Register model modules in Alembic metadata discovery.
5. Generate and review the initial migration before applying it
   locally.
6. Add tests for database models, constraints, and repository behavior.
7. Implement Cognito token validation and authorization boundaries.
8. Build car inventory behavior and tests.
9. Build booking lifecycle, hold expiry, concurrency safety, and
   inspection rules.
10. Integrate Stripe checkout and verified, idempotent webhook handling.
11. Add receipt/ticket snapshots and notifications.
12. Add asynchronous event processing and scheduled work where
    justified.
13. Containerize services and add CI checks.
14. Design and provision AWS infrastructure with least privilege.
15. Perform security, reliability, backup/restore, and end-to-end
    testing.
    This sequence is a working plan, not a guarantee that every stage is
    independent. Revisit ordering when implementation dependencies require
    it.
    Working conventions

- Explain the purpose of a file and important code decisions before
  introducing them.
- Prefer editing source files in the editor; use terminal commands for
  installing, running, migrating, and testing.
- Make one focused change at a time.
- Run the relevant tests after changes.
- Inspect generated migrations before applying them.
- Do not silently skip failing tests or suppress warnings without
  understanding them.
- Do not put real secrets in examples, logs, source control, or
  documentation.
- Record consequential decisions and changes in this document.

11. Testing Strategy
    The test suite should grow from simple endpoint tests into layered
    verification.
    Unit tests
    Test pure business rules such as price calculation, rental-period
    validation, permission decisions, state transitions, and event
    idempotency.
    API tests
    Test status codes, request/response schemas, authorization failures,
    validation errors, and expected API behavior.
    Database integration tests
    Test migrations, foreign keys, uniqueness and check constraints,
    transactional behavior, concurrent booking attempts, and persistence of
    historical snapshots.
    Payment and event tests
    Test invalid Stripe signatures, valid events, duplicate delivery,
    payment failure, retries, and reconciliation behavior without relying on
    live payments.
    End-to-end tests
    Verify a realistic journey: browse a car, create a booking, pay through
    a test integration, receive a ticket, complete the rental, and keep the
    car unavailable until inspection is approved.

Use isolated test data and test infrastructure. Do not run destructive
test operations against production data. 12. Open Decisions and Questions
These items need explicit decisions before their corresponding features
are finalized.

1. Identity data model: Which user/profile attributes, if any,
   should be stored locally in PostgreSQL in addition to Cognito's
   identity records?
2. Roles and permissions: Final roles, role assignment process, and
   permission matrix.
3. Service deployment: Which services need independent deployment
   initially, and which may be grouped operationally?
4. Vehicle schema: Required fields, vehicle categories, location,
   images, and maintenance state.
5. Pricing edge cases: Minimum duration, seconds/minutes handling,
   timezone policy, and exact rounding method.
6. Booking status machine: Exact statuses and permitted transitions
   for pending, paid/confirmed, active, completed, cancelled, expired,
   late, and inspection states.
7. Hold expiry: Scheduled processing approach and acceptable expiry
   delay.
8. Availability semantics: How to represent inspection failure,
   maintenance, damage, late return, and early return.
9. Deletion policy: When vehicle records may be archived versus
   physically deleted.
10. Payment policy: Refunds, payment retries, partial failures, and
    reconciliation schedule.
11. Receipt delivery: Email format, delivery retries, and whether
    customers can retrieve receipts from the API.
12. Notifications: Required events, channels, and templates.
13. AWS hosting details: Container runtime, network layout, database
    service, secrets, environments, and observability stack.
14. Data retention and privacy: Audit retention, personal-data
    deletion requests, and retention requirements for financial records.
    Do not treat unanswered questions as silently settled requirements.
    Document the chosen answer when it is decided.
15. Definition of Done
    A feature is not complete merely because its happy-path endpoint works.
    Depending on the feature, completion should include:

- Requirements and state transitions documented.
- Input validation and authorization enforced on the server.
- Database constraints and transaction boundaries considered.
- Failure and retry behavior defined.
- Automated tests for success and relevant failure paths.
- Migrations reviewed and tested.
- Logs and errors useful without exposing secrets or sensitive
  information.
- API behavior documented.
- Configuration and secrets handled safely.
- Relevant operational and monitoring needs considered.
  A release is production-ready only after deployment, security,
  observability, backup/restore, and end-to-end requirements have also
  been validated.

14. Change Log
    Date Change
    20 October 2026 Captured the product requirements,
    intended architecture, security
    principles, local development
    baseline, current auth-service
    implementation, tests, Alembic
    status, and open decisions.

20 October 2026 Confirmed two basic FastAPI
endpoint tests pass during the initial
auth-service foundation work, before
application migrations were added.

20 October 2026 Added the receipt service
with immutable rental snapshots,
idempotent creation, and a locally
applied database migration.

20 October 2026 Added shared Cognito token verification, server-priced
booking holds with vehicle snapshots and PostgreSQL overlap exclusion,
verified Stripe success confirmation for unexpired booking holds, and
idempotent receipt creation on verified payment. Added Compose
configuration for all six services and recorded remaining integration
and operational work.

20 October 2026 Changed customer checkout to accept only a booking ID and
retrieve price from the booking service. Added one-payment-per-booking
constraint and audited pickup, return, and inspection transitions.

20 October 2026 Added a service-key-protected verified customer contact
lookup and a PostgreSQL notification queue with retry leases and
exponential backoff. Verified payment events now queue receipt email.

20 October 2026 Added tests for payment amount validation, webhook retry
after downstream failure, duplicate event idempotency, and notification
retry scheduling. Verified the service-to-service email enqueue flow with
disposable local records and a mocked Stripe event.

20 October 2026 Added customer vehicle availability search and recorded
successful but unapplied Stripe charges for manual reconciliation when a
booking hold has expired or cannot be confirmed.

20 October 2026 Added a durable payment-delivery outbox. Verified success
webhooks now commit event deduplication and delivery work before acknowledging
Stripe; a leased worker retries booking confirmation, receipt creation, and
notification enqueueing with idempotent downstream keys. Added internal
failed-job inspection and recovery routes, and tests for retry, duplicate
webhooks, unapplied charges, and requeueing exhausted jobs.

15. How to Maintain This Document
Keep this file at:

docs/PROJECT_SPECIFICATION.md

Update it whenever a material product requirement, architecture
decision, service boundary, data model, security rule, deployment
choice, or development milestone changes. Keep the root README.md
concise and use it to point developers to this specification and the
service-specific READMEs.
