import json
#import logging
import re
from typing import List, Dict

class ComplianceChecker:
    def __init__(self, rules_path: str, vector_store, llm_client):
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.rules = self._load_rules(rules_path)
    
    def _load_rules(self, rules_path: str) -> List[Dict]:
        with open(rules_path, 'r') as f:
            data = json.load(f)
        return data.get('compliance_rules', [])

    # --- MODIFIED: Changed default n_context_docs from 5 to 15 to widen the FAISS net ---
    def check_single_rule(self, rule: Dict, n_context_docs: int = 15) -> Dict:
        if hasattr(self.llm_client, 'clear_cache'):
            self.llm_client.clear_cache()

        #criteria_list = rule.get('check_criteria', [])
        rule_keywords = rule.get("mandatory_keywords", [])
        keywords_str = " ".join(rule_keywords)
        
        # --- KEPT: Your preferred search query format ---
        # search_query = f"{rule['rule_name']} {', '.join(criteria_list)} {keywords_str}"
        
        # Diagnostic Query: Rule Name + Keywords (No Criteria Smokescreen)
        search_query = f"{rule['rule_name']} {keywords_str}"
        
        # Fetch chunks using the wider net (n_context_docs = 15)
        search_results = self.vector_store.search(query=search_query, n_results=n_context_docs)

        raw_docs = search_results.get('documents', [])
        raw_metas = search_results.get('metadatas', [])
        distances = search_results.get('distances', [])

        relevant_docs = raw_docs[0] if raw_docs and isinstance(raw_docs[0], list) else raw_docs
        metadatas = raw_metas[0] if raw_metas and isinstance(raw_metas[0], list) else raw_metas
        distances = distances[0] if distances and isinstance(distances[0], list) else distances

        if not relevant_docs:
            return self._empty_result(rule, "Clause not found in PDF.")

        # --- THE HYBRID RE-RANKER ---
        verified_docs = []
        verified_metas = []
        
        if rule_keywords:
            for doc, meta in zip(relevant_docs, metadatas):
                text_lower = doc.lower()
                if any(re.search(rf'\b{re.escape(k)}\b', text_lower) for k in rule_keywords):
                    verified_docs.append(doc)
                    verified_metas.append(meta)
            
            if not verified_docs:
                print(f"TRAP DOOR ACTIVATED: FAISS failed to find keywords for {rule['rule_id']}")
                return {
                    "rule_id": rule['rule_id'],
                    "rule_name": rule['rule_name'],
                    "status": "NON-COMPLIANT",
                    "evidence": "Clause not found.",
                    "analysis": f"Automated Evaluation: The document does not contain terminology related to {rule['rule_name']}.",
                    "source_documents": []
                }
        else:
            verified_docs = relevant_docs
            verified_metas = metadatas

        # --- KEPT: Only pass the top 2 VERIFIED chunks to protect LLM memory ---
        compliance_result = self.check_rule_compliance(rule=rule, context=verified_docs[:2])

        # 3. UNIVERSAL EVIDENCE VERIFICATION & PAGE MATCHER
        evidence_text = compliance_result.get("evidence", "")
        is_empty_evidence = evidence_text.lower().strip('. \n') in ["none", "clause not found", "unable to extract evidence", ""]
        
        
        if evidence_text and not is_empty_evidence:
            def normalize(t): return re.sub(r'\W+', '', t).lower()
            
            is_valid_evidence = False
            pages = set()
            
            # --- KEPT: Checking only the top 2 verified metas to exactly match what the LLM read ---
            for doc, meta in zip(verified_docs[:2], verified_metas[:2]):
                if isinstance(meta, dict):
                    norm_doc = normalize(doc)
                    norm_ev = normalize(evidence_text)
                    
                    # --- THE PAGE MATCHER ---
                    if len(norm_ev) < 30:
                        if norm_ev in norm_doc:
                            is_valid_evidence = True
                    else:
                        for i in range(0, len(norm_ev) - 30, 15):
                            slice_to_check = norm_ev[i:i+30]
                            if slice_to_check in norm_doc:
                                is_valid_evidence = True
                                break  
                    
                    if is_valid_evidence:
                        p = meta.get("page")
                        if p: pages.add(str(p))

            if is_valid_evidence:
                if pages:
                    p_str = ", ".join(sorted(list(pages), key=lambda x: int(x) if str(x).isdigit() else 0))
                    compliance_result["evidence"] = f"(Page {p_str}) {evidence_text}"
            else:
                compliance_result["status"] = "NON-COMPLIANT"
                compliance_result["analysis"] = "LLM indicated compliance, but the cited evidence was not found in the original document."
                compliance_result["evidence"] = "Invalid/Hallucinated quote."

        elif compliance_result["status"] == "COMPLIANT":
            compliance_result["status"] = "NON-COMPLIANT"
            compliance_result["analysis"] = "Status marked as compliant without supporting evidence."
            compliance_result["evidence"] = "Clause not found (Auto-Corrected)."

        compliance_result["source_documents"] = [{"content": d, "metadata": m} for d, m in zip(verified_docs[:2], verified_metas[:2])]
        return compliance_result
    
    def check_rule_compliance(self, rule: Dict, context: List[str]) -> Dict:
        context_text = "\n\n...\n\n".join(context[:2]) 
        rule_id = rule['rule_id']
        rule_keywords = rule.get("mandatory_keywords", [])

        # --- THE HARDENED TRAP DOOR ---
        if rule_keywords:
            text_lower = context_text.lower()
            has_keyword = any(re.search(rf'\b{re.escape(k)}\b', text_lower) for k in rule_keywords)
            
            if not has_keyword:
                print(f"🛑 TRAP DOOR ACTIVATED: Blocked LLM hallucination for {rule_id}")
                return {
                    "rule_id": rule_id,
                    "rule_name": rule['rule_name'],
                    "status": "NON-COMPLIANT",
                    "analysis": f"The contract does not contain terminology related to {rule['rule_name']}.",
                    "evidence": "Clause not found."
                }


        if rule['rule_id'] == 'R005':
            print(f"\n--- X-RAY: FAISS CHUNKS FOR R005 ---\n{context_text}\n------------------------------------\n")        
        

# EXACT QUOTE:"""

        system_msg = "You are a precise extraction tool. You only output exactly what is requested. NEVER generate numbered lists or bullet points."

        prompt = f"""Topic: {rule['rule_name']}
Keywords to look for: {', '.join(rule_keywords)}

Contract Text:
{context_text}

INSTRUCTIONS: 
1. Find the sentence or sentences in the Contract Text that contain any of the provided Keywords.
2. COPY AND PASTE ONLY those exact sentences. Do not summarize, do not alter words, and NEVER create a list.
3. If the keywords are present but completely unrelated to the Topic, output exactly: NONE.

EXACT QUOTE:"""        
        try:
            response = self.llm_client.generate(
                prompt=prompt, 
                system_msg=system_msg,
                temperature=0.0, 
                max_tokens=300,
                step_name=f"Audit {rule_id}"
            )
            
            safe_response = response.encode('ascii', errors='replace').decode('ascii')
            print(f"\n--- RAW LLM OUTPUT {rule['rule_id']} --- {rule['rule_name']}---\n{repr(safe_response)}\n---")

            # --- INSERT THE CLEANER HERE ---
            cleaned_response = self._clean_extracted_text(safe_response)

            # Pass the CLEANED text into your final parser
            return self._parse_compliance_response(cleaned_response, rule)

        except Exception as e:
            print(f"LLM Generation failed for {rule['rule_name']}: {e}")
            return self._empty_result(rule, "Processing error.")


    def _parse_compliance_response(self, raw_text: str, rule: Dict) -> Dict:
        result = {
            "rule_id": rule.get("rule_id", "Unknown"),
            "rule_name": rule.get("rule_name", "Unknown"),
            "status": "NON-COMPLIANT",
            "evidence": "Unable to extract evidence.",
            "analysis": "Automated Evaluation: System could not verify the clause."
        }

        try:
            clean_quote = re.sub(r'^(QUOTE:|OUTPUT:|\"|\')+|(\"|\')+$', '', raw_text.strip(), flags=re.IGNORECASE).strip()
            clean_quote = re.sub(r'\s+', ' ', clean_quote)
            
            clean_quote = clean_quote.replace("...", " ").replace(" . . . ", " ")

            if clean_quote.upper() in ["NONE", "NONE.", ""] or len(clean_quote) < 15:
                result["status"] = "NON-COMPLIANT"
                result["evidence"] = "Clause not found."
                result["analysis"] = f"Automated Evaluation: The required criteria for '{rule.get('rule_name')}' were not found."
                return result

            final_quote = clean_quote

            rule_keywords = rule.get("mandatory_keywords", [])
            if rule_keywords:
                quote_lower = final_quote.lower()
                has_keyword = any(re.search(rf'\b{re.escape(k)}\b', quote_lower) for k in rule_keywords)
                
                if not has_keyword:
                    print(f"🛑 FORCER ACTIVATED: Rejected lazy LLM quote for {rule['rule_id']}")
                    result["status"] = "NON-COMPLIANT"
                    result["evidence"] = "Clause not found."
                    result["analysis"] = f"Automated Evaluation: The extracted text did not contain the required legal terminology for '{rule.get('rule_name')}'."
                    return result

            result["status"] = "COMPLIANT"
            result["evidence"] = final_quote
            result["analysis"] = f"Automated Evaluation: System successfully located and extracted text matching the '{rule.get('rule_name')}' criteria."

        except Exception as e:
            print(f"Sanitizer caught error on {rule.get('rule_name')}: {e}")

        return result

    def _empty_result(self, rule, msg):
        return {"rule_id": rule['rule_id'], "rule_name": rule['rule_name'], "status": "UNCLEAR", "evidence": msg, "analysis": "Clause not found."}

    def get_compliance_summary(self, results: list) -> dict:
        summary = {"COMPLIANT": 0, "NON-COMPLIANT": 0, "UNCLEAR": 0, "TOTAL": len(results)}
        for r in results:
            status = r.get("status", "UNCLEAR")
            if status in summary:
                summary[status] += 1
            else:
                summary["UNCLEAR"] += 1
        
        if summary["TOTAL"] > 0:
            rate_percentage = (summary["COMPLIANT"] / summary["TOTAL"]) * 100
            summary["rate"] = f"{rate_percentage:.1f}%"
        else:
            summary["rate"] = "0%"
            
        return summary

    def _clean_extracted_text(self, text: str) -> str:
        # 1. First, cleanly remove normal prefixes so they don't trigger the guillotine
        text = re.sub(r'^(QUOTE:|OUTPUT:|EXACT QUOTE:|\"|\')+', '', text, flags=re.IGNORECASE).strip()
        
        # 2. THE GUILLOTINE: Now safely chop off trailing prompt leaks
        leak_pattern = r"(?i)(INSTRUCTIONS:|This text contains the following keywords:|This sentence contains the keyword|Note:)"
        text = re.split(leak_pattern, text)[0].strip()

        # 3. Clean up spaces
        text = re.sub(r'\s+', ' ', text)
        
        # 4. Split into sentences to detect and break loops
        sentences = re.split(r'(?<=[.!?])\s+', text)
        unique_sentences = []
        seen_content = set()
        
        for s in sentences:
            s_norm = re.sub(r'\W+', '', s).lower()
            if not s_norm: 
                continue
            if s_norm in seen_content:
                break
            if unique_sentences and len(s_norm) > 15 and s_norm in re.sub(r'\W+', '', unique_sentences[-1]).lower():
                break
                
            seen_content.add(s_norm)
            unique_sentences.append(s)
            
        return " ".join(unique_sentences).strip()
    

