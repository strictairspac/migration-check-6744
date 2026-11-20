"""Importing this package registers every model, so foreign keys resolve no
matter which module is imported first (API, worker or seed script)."""
from src.models import identity,batch,mapping,run,lab  # noqa: F401
