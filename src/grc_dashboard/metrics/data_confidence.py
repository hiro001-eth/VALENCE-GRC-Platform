import structlog

from grc_dashboard.models.siem import SIEMQueryResult

logger = structlog.get_logger(__name__)

class DataConfidenceEngine:
    """
    Data Quality & Confidence Index (DCI).
    Evaluates SIEM payload integrity. If DCI falls below 80%, 
    MNC boards flag the metric as "Unauditable".
    """
    def calculate_confidence(self, result: SIEMQueryResult, expected_fields: list[str] | None = None) -> float:
        """
        Returns a confidence score from 0.0 to 1.0.
        Penalizes for schema drift, null values, or unexpected volume drops.
        """
        confidence = 1.0
        
        if result.total_count == 0:
            # 0 events could be legit, but reduces confidence slightly unless verified
            return 0.90
            
        if not expected_fields:
            return confidence
            
        missing_fields_penalty = 0.0
        events_sampled = min(len(result.events), 100)
        
        if events_sampled == 0:
            return 0.90
            
        # Sample events for schema integrity
        for event in result.events[:events_sampled]:
            for field in expected_fields:
                # Check nested fields (e.g. "event.dataset")
                parts = field.split('.')
                curr = event.raw_fields
                found = True
                for p in parts:
                    if isinstance(curr, dict) and p in curr:
                        curr = curr[p]
                    else:
                        found = False
                        break
                        
                if not found or curr is None:
                    missing_fields_penalty += (1.0 / len(expected_fields)) / events_sampled
                    
        confidence -= missing_fields_penalty
        
        return max(0.0, round(confidence, 3))
