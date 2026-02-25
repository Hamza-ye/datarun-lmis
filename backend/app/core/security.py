from typing import List, Optional
from fastapi import Request, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

class ActorContext(BaseModel):
    """
    The stateless identity & access object extracted from the JWT.
    Passed down into Domain Services so they don't depend on HTTP request objects.
    """
    actor_id: str
    roles: List[str]
    allowed_nodes: List[str]

    def require_role(self, required_role: str):
        if required_role not in self.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Actor lacks required role: {required_role}"
            )

    def require_node_access(self, node_id: str):
        # In a real system, you would check if node_id is a child of any of allowed_nodes
        # utilizing the Shared Kernel's NodeRegistry. For MVP we check direct exact match.
        if "GLOBAL" in self.allowed_nodes:
            return
            
        if node_id not in self.allowed_nodes:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Actor does not have access to node: {node_id}"
            )


# Security Scheme for Swagger UI
security = HTTPBearer()

async def get_current_actor(credentials: HTTPAuthorizationCredentials = Security(security)) -> ActorContext:
    """
    Dependency Injection for FastAPI.
    In a real system, this would:
      1. Decode the JWT from credentials.credentials
      2. Verify the RS256 signature against the IdP's JWKS
      3. Extract claims
    
    For MVP, we simulate parsing a fake token.
    (We will use Mock patching in our Pytests to inject different actors).
    """
    token = credentials.credentials
    
    # --- MOCK IdP DECODING ---
    if token == "mock_external_system_token":
        return ActorContext(
            actor_id="system_dhis2_01",
            roles=["external_system"],
            allowed_nodes=[]
        )
    elif token == "mock_ledger_worker_token":
        return ActorContext(
            actor_id="ledger_system_worker",
            roles=["ledger_system"],
            allowed_nodes=[]
        )
    elif token == "mock_supervisor_token":
         return ActorContext(
            actor_id="user_supervisor_99",
            roles=["ledger_supervisor"],
            allowed_nodes=["DIST-A", "CLINIC_1"]
        )
    elif token == "mock_system_admin_token":
        return ActorContext(
            actor_id="admin_1",
            roles=["system_admin", "ledger_supervisor", "ledger_system"],
            allowed_nodes=["GLOBAL"]
        )
         
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
