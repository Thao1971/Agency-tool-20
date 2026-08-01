"""ARROBA Copilot — control de acceso multi-tenant (defensa en profundidad).

La auth base es service-to-service (`require_service_key`): hoy solo ARROBA tiene la clave. Esto añade,
por encima: (1) `tenant_id` obligatorio en operaciones con datos de usuario; (2) scoping opcional por
`allowed_tenants` del propio doc de la clave (si está, la clave solo puede operar sobre esos tenants);
(3) confirmación explícita para acciones sensibles (export/forget). Todo opcional-compatible: una clave
sin `allowed_tenants` sigue funcionando como antes.
"""

from typing import Dict, Optional
from fastapi import HTTPException, status


def _allowed(key_doc: Optional[Dict]):
    return (key_doc or {}).get("allowed_tenants")   # None → sin restricción


def assert_tenant(key_doc: Optional[Dict], tenant_id: Optional[str]) -> None:
    """Exige tenant_id y valida que la clave puede operar sobre ese tenant."""
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id requerido")
    allow = _allowed(key_doc)
    if allow is not None and tenant_id not in allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"La clave de servicio no tiene acceso al tenant '{tenant_id}'.")


def assert_confirm(confirm: bool) -> None:
    """Acciones sensibles (export/forget) requieren confirmación explícita."""
    if not confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Acción sensible: requiere confirm=true.")
