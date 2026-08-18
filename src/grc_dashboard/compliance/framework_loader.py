from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class ControlRequirement(BaseModel):
    id: str
    title: str
    description: str
    metric_ids: list[str] = Field(default_factory=list)


class ComplianceFrameworkRule(BaseModel):
    framework_name: str
    full_name: str
    version: str
    controls: list[ControlRequirement] = Field(default_factory=list)


class FrameworkLoader:
    """Loads and validates compliance framework rule definition files (YAML)."""

    def __init__(self, rules_dir: Path | None = None) -> None:
        if rules_dir is None:
            from grc_dashboard.config import get_settings
            settings = get_settings()
            self.rules_dir = settings.pipeline.output_dir.parent / "rules" / "frameworks"
        else:
            self.rules_dir = rules_dir

    def load_framework(self, name: str) -> ComplianceFrameworkRule | None:
        file_path = self.rules_dir / f"{name.lower()}.yaml"
        if not file_path.exists():
            logger.warning("framework_yaml_not_found", path=str(file_path))
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return ComplianceFrameworkRule.model_validate(data)
        except Exception as e:
            logger.error("framework_load_failed", name=name, error=str(e))
            return None

    def list_frameworks(self) -> list[str]:
        if not self.rules_dir.exists():
            return []
        return [p.stem.upper() for p in self.rules_dir.glob("*.yaml")]
