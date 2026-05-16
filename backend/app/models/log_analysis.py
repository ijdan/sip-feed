from pydantic import BaseModel, ConfigDict
from typing import Literal

Priorite = Literal["CRITIQUE", "HAUTE", "MOYENNE", "BASSE"]


class LogAnalysisItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    point_notable: str
    prompt_correction: str
    date: str
    priorite: Priorite


class LogAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str
    generated_at: str
    logs_count: int
    resume: str
    items: list[LogAnalysisItem] = []
