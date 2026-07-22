"""Handler registrations. Importing this package registers all job handlers."""

from services.jobs import registry
from services.jobs.handlers.ingest_handler import run_ingest
from services.jobs.handlers.master_handlers import (
    run_rebuild_master, run_rebuild_ownership_graph,
)

registry.register("ingest_iberinform", run_ingest)
registry.register("rebuild_master", run_rebuild_master)
registry.register("rebuild_ownership_graph", run_rebuild_ownership_graph)
