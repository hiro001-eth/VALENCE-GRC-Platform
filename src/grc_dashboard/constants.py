from enum import StrEnum

# RAG Status Mappings (ANCHOR:RAG_STATUS_MAP)
RAG_STATUS_MAP = {
    "Green": {"description": "Metric within acceptable risk range", "visual_encoding": "Green fill with checkmark icon"},
    "Amber": {"description": "Metric approaching risk threshold requiring attention", "visual_encoding": "Amber fill with warning icon"},
    "Red": {"description": "Metric exceeds risk threshold requiring immediate action", "visual_encoding": "Red fill with alert icon"},
    "Stale": {"description": "Data older than TTL — metric excluded from RAG", "visual_encoding": "Gray fill with clock icon and STALE banner"},
    "NoData": {"description": "SIEM query returned empty result or failed", "visual_encoding": "Gray fill with no-data icon and ERROR banner"}
}

# MITRE ATT&CK Tactics
MITRE_TACTICS_LIST = [
    "Reconnaissance", "Resource Development", "Initial Access", "Execution", 
    "Persistence", "Privilege Escalation", "Defense Evasion", "Credential Access", 
    "Discovery", "Lateral Movement", "Collection", "Command and Control", 
    "Exfiltration", "Impact"
]

# Metric Types
class METRIC_TYPES(StrEnum):
    KRI = "KRI"
    KPI = "KPI"

# CSV Output Columns (ANCHOR:csv_output_schema)
CSV_COLUMNS = [
    "metric_id", "metric_name", "metric_type", "value", "unit",
    "rag_status", "trend_direction", "trend_delta_percent",
    "data_freshness_utc", "is_stale", "siem_query_hash",
    "computation_formula_hash", "threshold_config_hash",
    "coverage_gap_count", "dashboard_run_id", "generated_at",
    "computation_timestamp_utc", "boundary_flag"
]

MAX_STALENESS_MINUTES = 30

class LogEventType(StrEnum):
    DASHBOARD_START = "DASHBOARD_START"
    DASHBOARD_COMPLETE = "DASHBOARD_COMPLETE"
    DASHBOARD_FAILED = "DASHBOARD_FAILED"
    SIEM_QUERY_START = "SIEM_QUERY_START"
    SIEM_QUERY_COMPLETE = "SIEM_QUERY_COMPLETE"
    SIEM_QUERY_FAILED = "SIEM_QUERY_FAILED"
    METRIC_COMPUTED = "METRIC_COMPUTED"
    METRIC_STALE = "METRIC_STALE"
    RAG_ASSIGNED = "RAG_ASSIGNED"
    TREND_CALCULATED = "TREND_CALCULATED"
    COVERAGE_MAPPED = "COVERAGE_MAPPED"
    COVERAGE_GAP_DETECTED = "COVERAGE_GAP_DETECTED"
    PDF_EXPORTED = "PDF_EXPORTED"
    PDF_VERIFIED = "PDF_VERIFIED"
    HEALTHCHECK_PASS = "HEALTHCHECK_PASS"
    HEALTHCHECK_FAIL = "HEALTHCHECK_FAIL"
    THRESHOLD_VIOLATION = "THRESHOLD_VIOLATION"
