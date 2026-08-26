from pydantic import BaseModel


class DemographicItem(BaseModel):
    name: str
    value: int


class DemographicChart(BaseModel):
    type: str
    name: str
    items: list[DemographicItem]
