"""Transaction OS — permanent execution infrastructure for corporate operations.

Owns (DTX1): transactional entities, state, declarative state machine, event log,
permissions, workflow runtime, auditability. Event Driven First (DTX13): state changes
ONLY via audited events. Multi-tenant (DTX9). See TRANSACTION_OS_ARCHITECTURE.md.
"""
