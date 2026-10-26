
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="GridCare API")


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


@app.get("/")
def home():
    return {"message": "Welcome to GridCare"}


@app.get("/api/substations", response_model=list[Substation])
def get_substations():
    return substations

@app.get("/api/substations/{substation_id}", response_model=Substation)
def get_substation(substation_id: int):
    for substation in substations:
        if substation.id == substation_id:
            return substation

    raise HTTPException(
        status_code=404,
        detail="Substation not found",
    )

@app.post(
    "/api/substations",
    response_model=Substation,
    status_code=status.HTTP_201_CREATED,
)
def create_substation(payload: SubstationCreate):
    new_id = max(
        (substation.id for substation in substations),
        default=0,
    ) + 1

    new_substation = Substation(
        id=new_id,
        **payload.model_dump(),
    )

    substations.append(new_substation)

    return new_substation


@app.put("/api/substations/{substation_id}", response_model=Substation)
def replace_substation(
    substation_id: int,
    payload: SubstationCreate,
):
    for index, substation in enumerate(substations):
        if substation.id == substation_id:
            updated_substation = Substation(
                id=substation_id,
                **payload.model_dump(),
            )

            substations[index] = updated_substation
            return updated_substation

    raise HTTPException(
        status_code=404,
        detail="Substation not found",
    )


@app.patch("/api/substations/{substation_id}", response_model=Substation)
def patch_substation(
    substation_id: int,
    payload: SubstationUpdate,
):
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update",
        )

    if any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=422,
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
        status_code=404,
        detail="Substation not found",
    )


@app.delete("/api/substations/{substation_id}", status_code=204)
def delete_substation(substation_id: int):
    for index, substation in enumerate(substations):
        if substation.id == substation_id:
            substations.pop(index)
            return

    raise HTTPException(
        status_code=404,
        detail="Substation not found",
    )