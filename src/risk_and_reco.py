#import logging
import re
from typing import Dict

class RiskAnalyser:
    def __init__(self, vector_store, llm_client):
        self.vector_store = vector_store
        self.llm_client = llm_client

    def process_single_risk(self, compliance_data: Dict) -> Dict:
        """Processes one rule at a time so the UI can update live."""
        
        rule_name = compliance_data.get('rule_name', 'Unknown Rule')
        status = compliance_data.get('status', 'UNKNOWN')
        evidence = compliance_data.get('evidence', 'No evidence provided.')

        # --- THE STRICT ALGORITHMIC PERSONA ---
        system_msg = "You are an elite Corporate Risk Consultant. You analyze legal compliance data and output strict, formatted business risk assessments. You do not explain or converse. You only output the requested format."

        # --- THE FILL-IN-THE-BLANK PROMPT ---
        prompt = f"""CONTRACT CLAUSE ANALYSIS:
Rule: {rule_name}
Compliance Status: {status}
Extracted Text: {evidence}

TASK:
Based on the Compliance Status and Extracted Text, assess the business risk.
- If Status is NON-COMPLIANT (clause missing), the risk is usually HIGH or MEDIUM.
- If Status is COMPLIANT, the risk is usually LOW, unless the extracted text contains highly unfavorable terms.

Provide exactly three outputs:
1. RISK LEVEL: Exactly HIGH, MEDIUM, or LOW.
2. BUSINESS IMPACT: 1 to 2 sentences explaining the financial or operational danger to the company.
3. RECOMMENDATION: 1 to 2 actionable steps to mitigate the risk or negotiate better terms.

OUTPUT FORMAT:
RISK LEVEL: 
BUSINESS IMPACT: 
RECOMMENDATION: """

        try:
            response = self.llm_client.generate(
                prompt=prompt, 
                system_msg=system_msg,
                temperature=0.1,  # Low temp prevents the model from getting creative/rambling
                step_name=f"Risk Analysis: {rule_name}"
            )
            
            safe_response = response.encode('ascii', errors='replace').decode('ascii')
            return self._parse_risk_output(safe_response, compliance_data)
            
        except Exception as e:
            print(f"Risk Analysis failed for {rule_name}: {e}")
            return self._fallback_report(rule_name)

    def _parse_risk_output(self, response: str, original_data: Dict) -> Dict:
        report = self._fallback_report(original_data.get("rule_name", "Clause Analysis"))

        # 1. Extract Risk Level
        risk_match = re.search(r"RISK LEVEL:\s*(HIGH|MEDIUM|LOW)", response, re.IGNORECASE)
        if risk_match:
            report["risk_level"] = risk_match.group(1).upper()
        else:
            # Fallback logic if LLM forgets the level but knows the status
            if original_data.get("status") == "NON-COMPLIANT":
                report["risk_level"] = "HIGH"
        
        # 2. Extract Business Impact
        impact_match = re.search(r"BUSINESS IMPACT:(.*?)(?=RECOMMENDATION:|$)", response, re.IGNORECASE | re.DOTALL)
        if impact_match:
            raw_impact = impact_match.group(1).strip()
            report["business_impact"] = self._clean_text(raw_impact)

        # 3. Extract Recommendation
        reco_match = re.search(r"RECOMMENDATION:(.*)", response, re.IGNORECASE | re.DOTALL)
        if reco_match:
            raw_reco = reco_match.group(1).strip()
            report["recommendation"] = self._clean_text(raw_reco)

        return report

    def _clean_text(self, text: str) -> str:
        """Removes LLM artifacts, trailing numbers, or weird spacing."""
        text = re.sub(r"^\d+\.\s*", "", text) # Remove leading "1." or "2."
        text = re.sub(r"\d+\.$", "", text)    # Remove trailing numbers like "3."
        text = re.sub(r'\s+', ' ', text)      # Flatten newlines into single spaces
        return text.strip()

    def _fallback_report(self, rule_name: str) -> Dict:
        """Provides a safe default if the LLM completely fails."""
        return {
            "rule_name": rule_name,
            "risk_level": "MEDIUM", 
            "business_impact": "Unable to automatically determine business impact due to processing error.",
            "recommendation": "Manual legal review recommended.",
        }