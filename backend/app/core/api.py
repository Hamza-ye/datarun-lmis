from fastapi import APIRouter, Depends

from app.core.security import ActorContext, get_current_actor

router = APIRouter(prefix="/api/auth", tags=["Authentication & Identity"])

@router.get("/me", response_model=ActorContext)
async def get_current_user_context(actor: ActorContext = Depends(get_current_actor)):
    """
    Returns the parsed JWT payload (ActorContext) for the current user.
    Used by the Angular SPA on bootstrap to determine RBAC visibility rules 
    (e.g., hiding the 'Admin' tab if they lack 'system_admin' role).
    """
    return actor
