"""Worker entrypoint — managed by Supervisor (`python -m services.jobs.worker`).

Separate process from the API. Registers all handlers, then consumes the queue forever.
Scale-out = run more instances of this program; the atomic claim keeps them coordinated.
"""

import os
import socket
import asyncio
import logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [worker] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("data_layer_worker")


async def main() -> None:
    from services.jobs import queue
    from services.jobs.runner import JobRunner
    import services.jobs.handlers  # noqa: F401  (registers handlers on import)

    await queue.ensure_indexes()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    await JobRunner(worker_id).run_forever()


if __name__ == "__main__":
    asyncio.run(main())
