"""Shared event loop for smoke tests that drive async code directly.

A single process-wide loop keeps the global motor client bound to one loop across all
test modules (creating a loop per module causes 'future belongs to a different loop').
"""

import asyncio

LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


def run_async(coro):
    return LOOP.run_until_complete(coro)
