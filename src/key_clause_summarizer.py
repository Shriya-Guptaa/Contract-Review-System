import json
import re
from typing import List, Dict

class KeyClauseSummary:
    def __init__(self, rules_path: str, vector_store, llm_client):
        self.vector_store = vector_store
        self.llm_client = llm_client
        self.summary_topics = self._load_topics(rules_path)

    def _load_topics(self, rules_path: str) -> List[Dict]:
        with open(rules_path, 'r') as f:
            data = json.load(f)
        rules = data.get('compliance_rules', [])
        return [r for r in rules if r.get("include_in_executive_summary") is True]

    def generate_single_summary(self, topic: Dict, n_context_docs: int = 15) -> Dict:
        if hasattr(self.llm_client, 'clear_cache'):
            self.llm_client.clear_cache()

        topic_name = topic.get('rule_name', 'Unknown Topic')
        topic_id = topic.get('rule_id', 'Unknown ID')
        keywords = topic.get("mandatory_keywords", [])
        
        # 1. FAISS Search (Wide Net, No Criteria)
        keywords_str = " ".join(keywords)
        search_query = f"{topic_name} {keywords_str}"
        
        search_results = self.vector_store.search(query=search_query, n_results=n_context_docs)
        raw_docs = search_results.get('documents', [])
        relevant_docs = raw_docs[0] if raw_docs and isinstance(raw_docs[0], list) else raw_docs

        if not relevant_docs:
            return {"rule_id": topic_id, "rule_name": topic_name, "summary": "This document does not appear to contain provisions regarding this topic."}

        # 2. Trap Door (Keyword Verification)
        verified_docs = []
        if keywords:
            for doc in relevant_docs:
                text_lower = doc.lower()
                if any(re.search(rf'\b{re.escape(k)}\b', text_lower) for k in keywords):
                    verified_docs.append(doc)
            
            if not verified_docs:
                print(f"🛑 SUMMARY TRAP DOOR ACTIVATED: Bypassed LLM for missing {topic_id}")
                return {
                    "rule_id": topic_id, 
                    "rule_name": topic_name, 
                    "summary": "This document does not contain explicit terms regarding this topic."
                }
        else:
            verified_docs = relevant_docs

        # 3. LLM Generation
        context_text = "\n\n...\n\n".join(verified_docs[:3]) 
        
        system_msg = "You are an expert Legal Executive Assistant. You write concise, plain-English summaries of contract clauses for non-lawyers."
        
        # Added a specific instruction to avoid repetition
        prompt = f"""Topic: {topic_name}

Contract Text:
{context_text}

INSTRUCTIONS:
Write a single, cohesive paragraph summarizing the key points regarding '{topic_name}'.
Keep it strictly factual and under 5 sentences.
Do not repeat yourself.

SUMMARY:"""

        try:
            response = self.llm_client.generate(
                prompt=prompt, 
                system_msg=system_msg,
                temperature=0.3, 
                step_name=f"Summarize {topic_id}"
            )
            
            safe_response = response.encode('ascii', errors='replace').decode('ascii').strip()
            
            # --- NEW PARSER FUNCTION CALLED HERE ---
            clean_summary = self._clean_summary_text(safe_response)
            
            # Fallback for empty/negative responses
            if clean_summary.lower() in ["none", "none.", ""] or "does not contain explicit terms" in clean_summary.lower():
                clean_summary = "This document does not contain explicit terms regarding this topic."

            return {"rule_id": topic_id, "rule_name": topic_name, "summary": clean_summary}

        except Exception as e:
            print(f"Summary Generation failed for {topic_name}: {e}")
            return {"rule_id": topic_id, "rule_name": topic_name, "summary": "Summary generation failed due to a processing error."}

    def _clean_summary_text(self, text: str) -> str:
        # 1. First, cleanly remove normal prefixes
        text = re.sub(r'^(QUOTE:|OUTPUT:|SUMMARY:|EXACT QUOTE:|\"|\')+', '', text, flags=re.IGNORECASE).strip()
        
        # 2. THE GUILLOTINE: Safely chop off trailing leaks
        leak_pattern = r"(?i)(INSTRUCTIONS:|This text contains the following keywords:|This sentence contains the keyword|Note:)"
        text = re.split(leak_pattern, text)[0].strip()

        # 3. Clean up spaces
        text = re.sub(r'\s+', ' ', text)
        
        # 4. Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        unique_sentences = []
        seen_content = set()
        
        for s in sentences:
            s_norm = re.sub(r'\W+', '', s).lower()
            if not s_norm:
                continue
            if s_norm in seen_content:
                break
            if unique_sentences and s_norm in re.sub(r'\W+', '', unique_sentences[-1]).lower():
                break
                
            seen_content.add(s_norm)
            unique_sentences.append(s)
            
            if len(unique_sentences) >= 6:
                break
        
        return " ".join(unique_sentences).strip()