"""Background asyncio workers that poll Postgres for queued work.

Per the project spec we deliberately avoid APScheduler / Celery / external
brokers — each worker is a coroutine launched from the FastAPI lifespan
hook and uses ``SELECT ... FOR UPDATE SKIP LOCKED`` to coordinate across
multiple API replicas without a queue."""
