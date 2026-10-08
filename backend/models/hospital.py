from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Resources(BaseModel):
    oxygenCylinders: int = 0
    icuBeds: int = 0
    ventilators: int = 0

class ConsumptionRate(BaseModel):
    oxygen: float = 0.0
    icu: float = 0.0

class Hospital(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    name: str
    location: str
    resources: Resources
    consumptionRate: ConsumptionRate
    lastUpdated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}