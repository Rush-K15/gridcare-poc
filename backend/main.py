import os
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError
from pydantic import BaseModel, Field


# Microsoft Entra ID configuration
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID")
GRIDCARE_API_CLIENT_ID = os.getenv("GRIDCARE_API_CLIENT_ID")

if not ENTRA_TENANT_ID or not GRIDCARE_API_CLIENT_ID:
    raise RuntimeError(
        "Missing ENTRA_TENANT_ID or GRIDCARE_API_CLIENT_ID environment variable"
    )

ENTRA_ISSUER = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0"
ENTRA_JWKS_URL = (
    f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"
)
REQUIRED_SCOPE = "access_as_user"
jwks_client = PyJWKClient(ENTRA_JWKS_URL)


app = FastAPI(title="GridCare API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def get_current_user(
    authorization: str | None = Header(default=None),
) -> dict:
    """Validate a Microsoft Entra access token and required delegated scope."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=GRIDCARE_API_CLIENT_ID,
            issuer=ENTRA_ISSUER,
            options={"require": ["exp", "iss", "aud", "tid"]},
        )
    except PyJWKClientConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach Microsoft's signing-key service",
        ) from None
    except (PyJWKClientError, PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if claims.get("tid") != ENTRA_TENANT_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token belongs to an unexpected tenant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check required application role
    roles = claims.get("roles", [])

    if "Substations.ReadWrite.All" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient application permissions",
        )

    return claims


# Data models
class Substation(BaseModel):
    id: int
    name: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=100)
    voltage_level: Literal["grid", "primary", "secondary"]
    status: Literal["operational", "maintenance", "fault"]


class SubstationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=100)
    voltage_level: Literal["grid", "primary", "secondary"]
    status: Literal["operational", "maintenance", "fault"]


class SubstationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    location: str | None = Field(default=None, min_length=2, max_length=100)
    voltage_level: Literal["grid", "primary", "secondary"] | None = None
    status: Literal["operational", "maintenance", "fault"] | None = None


# In-memory demo data
substations = [
    Substation(
        id=1,
        name="Northfield Primary Substation",
        location="Croydon",
        voltage_level="primary",
        status="operational",
    ),
    Substation(
        id=2,
        name="Riverside Grid Substation",
        location="Bromley",
        voltage_level="grid",
        status="maintenance",
    ),
]


# Routes
@app.get("/")
def home():
    return {"message": "Welcome to GridCare"}


@app.get("/api/auth-check")
def auth_check(current_user: dict = Depends(get_current_user)):
    return {
        "authenticated": True,
        "message": "Access token accepted for GridCare API",
    }


@app.get(
    "/api/substations",
    response_model=list[Substation],
    dependencies=[Depends(get_current_user)],
)
def get_substations():
    return substations


@app.get(
    "/api/substations/{substation_id}",
    response_model=Substation,
    dependencies=[Depends(get_current_user)],
)
def get_substation(substation_id: int):
    for substation in substations:
        if substation.id == substation_id:
            return substation

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Substation not found",
    )


@app.post(
    "/api/substations",
    response_model=Substation,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
)
def create_substation(payload: SubstationCreate):
    new_id = max((substation.id for substation in substations), default=0) + 1
    new_substation = Substation(id=new_id, **payload.model_dump())
    substations.append(new_substation)
    return new_substation


@app.put(
    "/api/substations/{substation_id}",
    response_model=Substation,
    dependencies=[Depends(get_current_user)],
)
def replace_substation(substation_id: int, payload: SubstationCreate):
    for index, substation in enumerate(substations):
        if substation.id == substation_id:
            updated_substation = Substation(
                id=substation_id,
                **payload.model_dump(),
            )
            substations[index] = updated_substation
            return updated_substation

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Substation not found",
    )


@app.patch(
    "/api/substations/{substation_id}",
    response_model=Substation,
    dependencies=[Depends(get_current_user)],
)
def patch_substation(substation_id: int, payload: SubstationUpdate):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    if any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fields cannot be null",
        )

    for index, substation in enumerate(substations):
        if substation.id == substation_id:
            updated_data = substation.model_dump()
            updated_data.update(changes)
            updated_substation = Substation(**updated_data)
            substations[index] = updated_substation
            return updated_substation

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Substation not found",
    )


@app.delete(
    "/api/substations/{substation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
def delete_substation(substation_id: int):
    for index, substation in enumerate(substations):
        if substation.id == substation_id:
            substations.pop(index)
            return None

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Substation not found",
    )
