import math
import random

import structlog

from grc_dashboard.models.metric import MetricDefinition

logger = structlog.get_logger(__name__)

class FAIREngine:
    """
    Factor Analysis of Information Risk (FAIR) quantification engine.
    Translates operational metrics into Board-level financial Value-at-Risk (VaR).
    Used daily by MNCs to prioritize budget based on $ exposure.
    Now enhanced with Monte Carlo statistical simulations.
    """
    
    def calculate_annualized_loss_expectancy(self, definition: MetricDefinition, current_value: float, rag_status: str) -> float:
        """
        Calculates ALE based on the FAIR ontology using the average exposure from the Monte Carlo simulation.
        """
        res = self.simulate_risk(definition, current_value, rag_status)
        return res["average_exposure"]

    def simulate_risk(self, definition: MetricDefinition, current_value: float, rag_status: str, iterations: int = 1000) -> dict[str, float]:
        """
        Runs a Monte Carlo simulation of financial exposure using FAIR parameters.
        - Threat Event Frequency modeled via Poisson distribution.
        - Loss Magnitude modeled via Log-Normal distribution.
        - Vulnerability modeled via Gaussian distribution around base control effectiveness.
        """
        # Save random state to prevent side effects and ensure reproducibility
        state = random.getstate()
        random.seed(hash(definition.metric_id) & 0xffffffff)
        
        tef = definition.fair_threat_event_frequency
        loss_mag = definition.fair_loss_magnitude_usd
        
        if loss_mag <= 0 or tef <= 0:
            random.setstate(state)
            return {"average_exposure": 0.0, "var_95": 0.0, "probability_of_breach": 0.0}
            
        # Vulnerability base
        base_vuln = 0.05
        if rag_status == "Amber":
            base_vuln = 0.40
        elif rag_status == "Red":
            base_vuln = 0.85
        elif rag_status in ("Stale", "NoData"):
            base_vuln = 1.00
            
        time_penalty_multiplier = 1.0
        if "MTT" in definition.metric_id:
            time_penalty_multiplier = max(1.0, current_value)
            
        # Log-Normal parameters for Loss Magnitude: Mean = exp(mu + sigma^2 / 2)
        sigma = 0.5
        mu = math.log(loss_mag) - (sigma ** 2 / 2)
        
        def poisson_sample(lmbda: float) -> int:
            if lmbda <= 0:
                return 0
            if lmbda > 30:
                val = random.gauss(lmbda, math.sqrt(lmbda))
                return max(0, int(round(val)))
            L = math.exp(-lmbda)
            k = 0
            p = 1.0
            while p > L and k < 1000:
                k += 1
                p *= random.random()
            return k - 1
            
        sim_ales = []
        breach_count = 0
        breach_threshold = 1000000.0  # $1M is standard board breach reporting limit
        
        for _ in range(iterations):
            tef_sample = poisson_sample(tef)
            vuln_sample = max(0.0, min(1.0, random.gauss(base_vuln, 0.05)))
            loss_sample = random.lognormvariate(mu, sigma)
            
            sample_ale = tef_sample * vuln_sample * (loss_sample * time_penalty_multiplier)
            sim_ales.append(sample_ale)
            
            if sample_ale > breach_threshold:
                breach_count += 1
                
        sim_ales.sort()
        avg_exposure = sum(sim_ales) / iterations
        var_95 = sim_ales[int(0.95 * iterations)]
        prob_breach = breach_count / iterations
        
        random.setstate(state)
        
        return {
            "average_exposure": round(avg_exposure, 2),
            "var_95": round(var_95, 2),
            "probability_of_breach": round(prob_breach, 4)
        }
