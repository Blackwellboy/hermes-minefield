"""Public catalogue-only routes. No credentials, private state or mutations.

The host mounts these behind its own plugin enablement/auth gates. Until a public
actor scope contract is verified, no owner-only data or privileged POST exists.
"""

from fastapi import APIRouter, HTTPException

from hermes_minefield.service.workspace import Workspace

router = APIRouter()


@router.get("/workspace")
def workspace():
    return Workspace().home()


@router.get("/checks")
def checks():
    return Workspace().checks()


@router.get("/privacy")
def privacy():
    return Workspace().privacy()


@router.post("/preview")
def preview(body: dict):
    try:
        return Workspace().action("preview", body)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid selection") from None
