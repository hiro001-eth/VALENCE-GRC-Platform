
class DashboardBaseException(Exception):
    """Base exception for all VALENCE pipeline errors with structlog context."""
    def __init__(self, message: str, correlation_id: str = "unknown", stage_name: str = "unknown", dashboard_run_id: str = "unknown"):
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id
        self.stage_name = stage_name
        self.dashboard_run_id = dashboard_run_id

# ----------------- SIEM Exceptions -----------------

class SIEMException(DashboardBaseException):
    pass

class SIEMQueryException(SIEMException):
    def __init__(self, message: str, query_hash: str, **kwargs): # type: ignore
        super().__init__(message, **kwargs)
        self.query_hash = query_hash

class SIEMSchemaValidationError(SIEMException):
    def __init__(self, message: str, field_path: str, raw_value: str, **kwargs): # type: ignore
        super().__init__(message, **kwargs)
        self.field_path = field_path
        self.raw_value = raw_value

class StaleMetricException(SIEMException):
    def __init__(self, message: str, age_minutes: float, **kwargs): # type: ignore
        super().__init__(message, **kwargs)
        self.age_minutes = age_minutes

class SIEMAuthenticationException(SIEMException):
    pass

class SIEMRateLimitException(SIEMException):
    def __init__(self, message: str, retry_after: int, **kwargs): # type: ignore
        super().__init__(message, **kwargs)
        self.retry_after = retry_after

# ----------------- Metric Exceptions -----------------

class MetricException(DashboardBaseException):
    pass

class MetricComputationException(MetricException):
    pass

class FPRFormulaException(MetricException):
    pass

class TrendCalculationException(MetricException):
    pass

class MissingMetricException(MetricException):
    pass

# ----------------- Classification Exceptions -----------------

class ClassificationException(DashboardBaseException):
    pass

class RAGAssignmentException(ClassificationException):
    pass

class ThresholdFrozenException(ClassificationException):
    pass

class ThresholdOverrideException(ClassificationException):
    pass

# ----------------- MITRE Exceptions -----------------

class MITREException(DashboardBaseException):
    pass

class STIXLoadException(MITREException):
    pass

class CoverageMappingException(MITREException):
    pass

class STIXSchemaValidationError(MITREException):
    pass

# ----------------- Rendering & Export Exceptions -----------------

class RenderException(DashboardBaseException):
    pass

class DashboardRenderException(RenderException):
    pass

class PDFExportException(RenderException):
    pass

class TemplateLoadException(RenderException):
    pass

class ExportException(DashboardBaseException):
    pass

class NullRateViolationException(ExportException):
    pass

class FileWriteException(ExportException):
    pass

# ----------------- Audit Exceptions -----------------

class AuditException(DashboardBaseException):
    pass

class HealthCheckFailedException(AuditException):
    pass

class LineageBreachException(AuditException):
    pass

class ConfigCorruptException(AuditException):
    pass
