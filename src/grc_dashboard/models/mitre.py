
from pydantic import BaseModel, ConfigDict


class TechniqueCoverage(BaseModel):
    technique_id: str
    technique_name: str
    tactic: str
    coverage_score: float  # 0.0 to 1.0
    mapped_rules: list[str]
    gap_flag: bool

    model_config = ConfigDict(frozen=True)

class CoverageMatrix(BaseModel):
    tactics: list[str]
    techniques: list[TechniqueCoverage]
    overall_coverage: float
    gap_count: int
    matrix_hash: str

    model_config = ConfigDict(frozen=True)

class DetectionRuleMapping(BaseModel):
    rule_id: str
    rule_name: str
    technique_ids: list[str]
    confidence: float

    model_config = ConfigDict(frozen=True)
