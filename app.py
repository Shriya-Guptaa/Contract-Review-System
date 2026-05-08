import streamlit as st
import os
import sys
import hashlib
import json
import time
from pathlib import Path
from dotenv import load_dotenv


# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))

from src.pdf_processor import PDFProcessor
from src.vector_store import VectorStore
from src.llm_client import LLMClient
from src.key_clause_summarizer import KeyClauseSummary
from src.compliance_checker import ComplianceChecker
from src.risk_and_reco import RiskAnalyser
from src.report_generator import PDFReportGenerator

class ContractAnalyser:
    """Main system orchestrator for Analysis and Chatbot"""
    
    def __init__(self):
        load_dotenv()
        self.initialize_session_state()
        self.initialize_llm()
        
        # Initialize Processor
        if 'pdf_processor' not in st.session_state:
            st.session_state.pdf_processor = PDFProcessor()
        self.pdf_processor = st.session_state.pdf_processor
        
        # Initialize Helper Classes
        self.key_clause_summarizer = KeyClauseSummary(
            rules_path="./config/compliance_rules.json",
            vector_store=None, 
            llm_client=self.llm_client
        )
        
        self.compliance_checker = ComplianceChecker(
            rules_path="./config/compliance_rules.json",
            vector_store=None, 
            llm_client=self.llm_client
        )

    def initialize_llm(self):
        """Persistent LLM loading"""
        if 'llm_client' not in st.session_state:
            with st.spinner("💾 Loading Local Mistral (5GB) into RAM..."):
                st.session_state.llm_client = LLMClient()
        self.llm_client = st.session_state.llm_client

    def initialize_session_state(self):
        """Ensures all data persists across Streamlit reruns"""
        defaults = {
            'analysis_complete': False,
            'analysis_results': {},
            'summaries': {},
            'active_collection': None,
            'contract_name': "",
            'chat_history': [],
            'pdf_bytes': None,
            'current_match_index': 0, # Added for Tab 4
            'search_results': []      # Added for Tab 4
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val

    def ingest_and_process(self, uploaded_file):
        """Ingest, save temp file, and index."""
        
        # 1. Save to Disk (CRITICAL for Tab 4 PDF Viewer)
        with open("temp_uploaded.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        # 2. Load into RAM for other tools (CRITICAL for Step 1/2)
        uploaded_file.seek(0)
        st.session_state.pdf_bytes = uploaded_file.read()
        uploaded_file.seek(0)
        
        # 3. Create Hash & Collection Name
        file_hash = hashlib.sha256(st.session_state.pdf_bytes).hexdigest()
        collection_name = f"contract_{file_hash[:12]}"
        st.session_state.active_collection = collection_name
        
        # 4. Vector Store Ingestion
        # We initialize the store with the new collection name
        store = VectorStore(
            persist_directory=os.getenv("VECTOR_STORE_PATH", "./data/vector_store"),
            collection_name=collection_name
        )

        if not store.collection_exists():
            with st.spinner("📥 Ingesting and Indexing Contract..."):
                # Uses the NEW PDFProcessor to get chunks WITH coordinates
                chunks = self.pdf_processor.process_uploaded_pdf(uploaded_file, uploaded_file.name)
                store.add_documents(chunks)
        
        return True

def reset_app_state():
    """Clears all generated data from the session state when a new file is loaded."""
    keys_to_delete = [
        'summary_results',       # Tab 1 ghosts
        'compliance_results',    # Tab 2 ghosts
       
    ]
    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]

def main():
    st.set_page_config(page_title="AI Contract Specialist", layout="wide", page_icon="⚖️")
    
    # Initialize the Analyser (which sets up Session State)
    analyser = ContractAnalyser()

    # --- NEW: GLOBAL LOCK STATE ---
    if 'is_processing' not in st.session_state:
        st.session_state.is_processing = False


    # Sidebar
    with st.sidebar:
        st.title("⚖️ Control Panel")
        uploaded_file = st.file_uploader("Upload Contract PDF", type=['pdf'], disabled=st.session_state.is_processing)
        if uploaded_file:
            if st.button("🚀 Ingest & Start Session", disabled=st.session_state.is_processing):
                st.session_state.analysis_results = {} 
                st.session_state.current_ai_answer = ""
                analyser.ingest_and_process(uploaded_file)
                st.session_state.analysis_complete = True
                st.session_state.contract_name = uploaded_file.name
                st.rerun()

        pdf_hash = st.session_state.get('active_collection')
        if pdf_hash:
            # Check if files exist on disk OR in memory
            sum_exists = os.path.exists(f"data/results/summary_{pdf_hash}.json") or 'key_clauses' in st.session_state.analysis_results
            comp_exists = os.path.exists(f"data/results/compliance_{pdf_hash}.json") or 'compliance_results' in st.session_state.analysis_results
            risk_exists = os.path.exists(f"data/results/risk_{pdf_hash}.json") or 'risk_results' in st.session_state.analysis_results

            if sum_exists and comp_exists and risk_exists:
                st.divider()
                st.subheader("Export Analysis")
                if st.button("Prepare Final PDF Report", type="primary", use_container_width=True):
                    with st.spinner("Compiling report..."):
                        # Ensure data is loaded into memory for the generator
                        res = st.session_state.analysis_results
                        if 'key_clauses' not in res:
                            with open(f"data/results/summary_{pdf_hash}.json", "r") as f: res['key_clauses'] = json.load(f)
                        if 'compliance_results' not in res:
                            with open(f"data/results/compliance_{pdf_hash}.json", "r") as f: res['compliance_results'] = json.load(f)
                        if 'risk_results' not in res:
                            with open(f"data/results/risk_{pdf_hash}.json", "r") as f: res['risk_results'] = json.load(f)
                        
                        generator = PDFReportGenerator()
                        # Generate the raw bytearray
                        raw_pdf_data = generator.generate(st.session_state.contract_name, res)
                        
                        
                        pdf_bytes = bytes(raw_pdf_data) 
                        
                        st.download_button(
                            label="Download Legal Report",
                            data=pdf_bytes,
                            file_name=f"Analysis_Report_{st.session_state.contract_name}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

    if not st.session_state.get('analysis_complete', False):
        st.info("Please upload a PDF in the sidebar and click 'Ingest & Start Session'.")
        return

    # Tabs for the Dashboard
    tab1, tab2, tab3= st.tabs(["📜 Summaries", "🛡️ Compliance", "⚠️ Risk Analysis & Reco"])

    # --- TAB 1: KEY CLAUSE SUMMARIES ---
    with tab1:
        st.subheader("Key Clause Summaries")
        
        # --- 3-STAGE STATE MACHINE ---
        if 'sum_run_stage' not in st.session_state:
            st.session_state.sum_run_stage = 0
            
        pdf_hash = st.session_state.active_collection
        summary_filepath = os.path.join("data", "results", f"summary_{pdf_hash}.json")
        
        if os.path.exists(summary_filepath):
            with st.container(border=True):
                st.write("**Executive Summary from a previous run exists**")
                sc1, sc2, sc3 = st.columns([2.5, 1, 3])
                
                with sc1:
                    sum_choice = st.radio(
                        "Summary Action", 
                        ["Load Previous Summary", "Run Summary Again"], 
                        horizontal=True, 
                        label_visibility="collapsed",
                        disabled=(st.session_state.sum_run_stage > 0) or st.session_state.is_processing
                    )
                with sc2:
                    execute_btn = st.button("Proceed", type="secondary", key="proceed_sum", disabled=(st.session_state.sum_run_stage > 0) or st.session_state.is_processing)
            
            trigger_load = execute_btn and sum_choice == "Load Previous Summary"
            
            # --- TRIGGER STAGE 1 ---
            if execute_btn and sum_choice == "Run Summary Again":
                st.session_state.sum_run_stage = 1
                st.rerun()
        else:
            if st.button("🔍 Generate Executive Summary", disabled=(st.session_state.sum_run_stage > 0) or st.session_state.is_processing):
                st.session_state.sum_run_stage = 1
                st.rerun()
            trigger_load = False

        master_summary_placeholder = st.empty()

        def render_summary_card(res, container_obj):
            with container_obj.expander(f"**{res['rule_id']}: :blue[{res['rule_name']}]**", expanded=True):
                safe_summary = res['summary'].replace('$', '\\$')
                is_missing = "does not contain explicit terms" in safe_summary.lower() or "appear to contain" in safe_summary.lower()
                
                if is_missing:
                    st.markdown(f":red[*{safe_summary}*]")
                else:
                    st.markdown(f"<span style='color: green;'>{safe_summary}</span>", unsafe_allow_html=True)

        if trigger_load:
            with open(summary_filepath, "r", encoding="utf-8") as f:
                st.session_state.analysis_results['key_clauses'] = json.load(f)

        # --- STAGE 1: FORCE WIPE ---
        if st.session_state.sum_run_stage == 1:
            if 'key_clauses' in st.session_state.analysis_results:
                del st.session_state.analysis_results['key_clauses']
            st.session_state.sum_run_stage = 2
            st.session_state.is_processing = True
            st.rerun()

        # --- STAGE 2: EXECUTE ---
        if st.session_state.sum_run_stage == 2:
            #st.session_state.is_processing = True 
            
            # Destroy the old elements before starting the spinner!
            master_summary_placeholder.empty()
            time.sleep(0.1) # Forces the browser to repaint the empty screen!
            try:
                with master_summary_placeholder.container():
                    store = VectorStore(collection_name=pdf_hash)
                    summarizer_engine = KeyClauseSummary(
                        rules_path="./config/compliance_rules.json",
                        vector_store=store,
                        llm_client=st.session_state.llm_client
                    )
                    
                    if not summarizer_engine.summary_topics:
                        st.warning("No topics flagged for summary.")
                    else:
                        with st.spinner("Synthesizing plain English summaries..."):
                            all_summaries = []
                            live_container = st.container() 
                            
                            for topic in summarizer_engine.summary_topics[:]:
                                res = summarizer_engine.generate_single_summary(topic, n_context_docs=15)
                                all_summaries.append(res)
                                render_summary_card(res, live_container)
                            
                            st.session_state.analysis_results['key_clauses'] = all_summaries
                            
                            os.makedirs(os.path.join("data", "results"), exist_ok=True)
                            with open(summary_filepath, "w", encoding="utf-8") as f:
                                json.dump(all_summaries, f, indent=4)
                            st.toast(f"Summary securely saved to {summary_filepath}")
            finally:
                st.session_state.sum_run_stage = 0 
                st.session_state.is_processing = False 
                st.rerun() 

        # --- STAGE 0: IDLE DISPLAY ---
        elif 'key_clauses' in st.session_state.analysis_results and st.session_state.sum_run_stage == 0:
            display_container = master_summary_placeholder.container()
            for res in st.session_state.analysis_results['key_clauses']:
                render_summary_card(res, display_container)

    # --- TAB 2: COMPLIANCE CHECK ---
    with tab2:
        st.subheader("Compliance Check")
        
        # --- NEW: TRUE 3-STAGE RUNNER ---
        # 0 = Idle/Display, 1 = Force Wipe Screen, 2 = Run AI
        if 'comp_run_stage' not in st.session_state:
            st.session_state.comp_run_stage = 0
            
        pdf_hash = st.session_state.active_collection
        compliance_filepath = os.path.join("data", "results", f"compliance_{pdf_hash}.json")
        
        if os.path.exists(compliance_filepath):
            with st.container(border=True):
                st.write("**Compliance Audit from a previous run exists**")
                cc1, cc2, cc3 = st.columns([2.5, 1, 3])
                
                with cc1:
                    comp_choice = st.radio(
                        "Compliance Action", 
                        ["Load Previous Audit", "Run Audit Again"], 
                        horizontal=True, 
                        label_visibility="collapsed",
                        disabled=(st.session_state.comp_run_stage > 0) or st.session_state.is_processing
                    )
                with cc2:
                    execute_btn = st.button("Proceed", type="secondary", key="proceed_comp", disabled=(st.session_state.comp_run_stage > 0) or st.session_state.is_processing)
            
            trigger_load = execute_btn and comp_choice == "Load Previous Audit"
            
            # --- TRIGGER STAGE 1 ---
            if execute_btn and comp_choice == "Run Audit Again":
                st.session_state.comp_run_stage = 1
                st.rerun()
        else:
            if st.button("Run Compliance Audit", disabled=(st.session_state.comp_run_stage > 0) or st.session_state.is_processing):
                st.session_state.comp_run_stage = 1
                st.rerun()
            trigger_load = False

        master_comp_placeholder = st.empty()

        def render_compliance_expander(res, container_obj, expanded=False):
            is_compliant = res.get('status', '').upper() == 'COMPLIANT'
            status_color = "green" if is_compliant else "red"
            header_text = f"**{res['rule_id']}: :blue[{res['rule_name']}] - :{status_color}[{res['status']}]**"
            
            with container_obj.expander(header_text, expanded=expanded):
                evidence_text = res['evidence']
                ev_color = "green" if is_compliant else "red"
                st.markdown(f"**:blue[Evidence:]** :{ev_color}[{evidence_text}]")

        if trigger_load:
            with open(compliance_filepath, "r", encoding="utf-8") as f:
                st.session_state.analysis_results['compliance_results'] = json.load(f)

        # --- STAGE 1: FORCE THE BROWSER WIPE ---
        if st.session_state.comp_run_stage == 1:
            if 'compliance_results' in st.session_state.analysis_results:
                del st.session_state.analysis_results['compliance_results']
            st.session_state.comp_run_stage = 2
            #TURN ON THE LOCK HERE! Before the rerun!
            st.session_state.is_processing = True
            st.rerun() # This absolutely forces the browser to render the empty screen!

        # --- STAGE 2: RUN AI ON TRULY BLANK SCREEN ---
        if st.session_state.comp_run_stage == 2:
            # THE TRUE GHOST KILLER 
            master_comp_placeholder.empty()
            time.sleep(0.1) # Forces the browser to repaint the empty screen! 
            try:
                with master_comp_placeholder.container():
                    store = VectorStore(collection_name=pdf_hash)
                    checker = ComplianceChecker(rules_path="./config/compliance_rules.json", vector_store=store, llm_client=st.session_state.llm_client)
                    
                    with st.spinner("Checking legal rules..."):
                        summary_header = st.empty() 
                        live_container = st.container() 
                        
                        all_results = []
                        for rule in checker.rules[:]:
                            res = checker.check_single_rule(rule, n_context_docs=15)
                            all_results.append(res)
                            st.session_state.llm_client.clear_cache()
                            render_compliance_expander(res, live_container, expanded=True)
                            
                        st.session_state.analysis_results['compliance_results'] = all_results
                        
                        os.makedirs(os.path.join("data", "results"), exist_ok=True)
                        with open(compliance_filepath, "w", encoding="utf-8") as f:
                            json.dump(all_results, f, indent=4)
                        
                        summary = checker.get_compliance_summary(all_results)
                        st.session_state.analysis_results['compliance_summary'] = summary
                        summary_header.success(f"**Audit Complete! Score:** {summary['rate']}")
                        st.toast(f"Results safely stored in {compliance_filepath}")
            finally:
                st.session_state.comp_run_stage = 0 # Reset to idle
                st.session_state.is_processing = False 
                st.rerun() 

        # --- STAGE 0: IDLE / PERSISTENT DISPLAY ---
        elif 'compliance_results' in st.session_state.analysis_results and st.session_state.comp_run_stage == 0:
            display_container = master_comp_placeholder.container()
            comp_results = st.session_state.analysis_results['compliance_results']
            compliant_count = sum(1 for r in comp_results if r['status'] == 'COMPLIANT')
            total = len(comp_results)
            rate_str = f"{int((compliant_count / total) * 100)}%" if total > 0 else "0%"
            
            display_container.success(f"**Audit Complete! Score:** {rate_str}")
            
            if 'comp_expand_all' not in st.session_state:
                st.session_state.comp_expand_all = False
            def toggle_expanders():
                st.session_state.comp_expand_all = not st.session_state.comp_expand_all
                
            col1, col2 = display_container.columns([5, 1])
            with col2:
                btn_label = "🔼 Collapse All" if st.session_state.comp_expand_all else "🔽 Expand All"
                st.button(btn_label, on_click=toggle_expanders, key="toggle_comp_btn")
            
            for res in comp_results:
                render_compliance_expander(res, display_container, expanded=st.session_state.comp_expand_all)


    # --- TAB 3: RISK & RECO ---
    with tab3:
        st.subheader("Business Risk Analysis & De-risking Advice")
        
        # --- 3-STAGE STATE MACHINE ---
        if 'risk_run_stage' not in st.session_state:
            st.session_state.risk_run_stage = 0
            
        pdf_hash = st.session_state.active_collection
        compliance_filepath = os.path.join("data", "results", f"compliance_{pdf_hash}.json")
        risk_filepath = os.path.join("data", "results", f"risk_{pdf_hash}.json")
        
        if os.path.exists(risk_filepath):
            with st.container(border=True):
                st.write("**Previous Result of Risk Analysis is available**")
                rc1, rc2, rc3 = st.columns([2.5, 1, 3])
                
                with rc1:
                    risk_choice = st.radio(
                        "Risk Action", 
                        ["View previous result", "Run New Risk Analysis"], 
                        horizontal=True, 
                        label_visibility="collapsed",
                        disabled=(st.session_state.risk_run_stage > 0) or st.session_state.is_processing
                    )
                with rc2:
                    execute_btn = st.button("Proceed", type="secondary", key="proceed_risk", disabled=(st.session_state.risk_run_stage > 0) or st.session_state.is_processing)
            
            trigger_load = execute_btn and risk_choice == "View previous result"
            
            # --- TRIGGER STAGE 1 ---
            if execute_btn and risk_choice == "Run New Risk Analysis":
                st.session_state.risk_run_stage = 1
                st.rerun()
        else:
            if st.button("⚠️ Run Risk Analysis", disabled=(st.session_state.risk_run_stage > 0) or st.session_state.is_processing):
                st.session_state.risk_run_stage = 1
                st.rerun()
            trigger_load = False

        master_risk_placeholder = st.empty()

        def render_risk_card(risk_data, container_obj):
            risk_lvl = risk_data.get('risk_level', 'LOW').upper()
            color_map = {"HIGH": "red", "MEDIUM": "blue", "LOW": "green"}
            c_color = color_map.get(risk_lvl, "green")
            
            with container_obj.container(border=True):
                c1, c2 = st.columns([1, 4])
                with c1:
                    st.caption("Risk Level")
                    st.markdown(f"### :{c_color}[{risk_lvl}]")
                with c2:
                    st.write(f"**{risk_data.get('rule_name', 'Clause')}**")
                    st.write(f"**Impact:** {risk_data.get('business_impact', 'N/A')}")
                    st.info(f"**Recommendation:** {risk_data.get('recommendation', 'N/A')}")

        if trigger_load:
            with open(risk_filepath, "r", encoding="utf-8") as f:
                st.session_state.analysis_results['risk_results'] = json.load(f)

        # --- STAGE 1: FORCE WIPE ---
        if st.session_state.risk_run_stage == 1:
            if not os.path.exists(compliance_filepath):
                st.error("Please run Compliance Check first. No saved audit found for this document.")
                st.session_state.risk_run_stage = 0
            else:
                if 'risk_results' in st.session_state.analysis_results:
                    del st.session_state.analysis_results['risk_results']
                st.session_state.risk_run_stage = 2
                # TURN ON THE LOCK HERE! Before the rerun!
                st.session_state.is_processing = True
                st.rerun()

        # --- STAGE 2: EXECUTE ---
        if st.session_state.risk_run_stage == 2:
            # THE GHOST KILLER
            master_risk_placeholder.empty()
            time.sleep(0.1) # Forces the browser to repaint the empty screen!         
            try:
                with master_risk_placeholder.container():
                    with open(compliance_filepath, "r", encoding="utf-8") as f:
                        compliance_data = json.load(f)
                    
                    risk_engine = RiskAnalyser(None, st.session_state.llm_client)
                    all_risks = []
                    
                    with st.spinner("Assessing business risks..."):
                        summary_header = st.empty()
                        live_container = st.container()
                        
                        for comp_res in compliance_data:
                            risk = risk_engine.process_single_risk(comp_res)
                            all_risks.append(risk)
                            st.session_state.llm_client.clear_cache()
                            render_risk_card(risk, live_container)

                        st.session_state.analysis_results['risk_results'] = all_risks
                        
                        os.makedirs(os.path.join("data", "results"), exist_ok=True)
                        with open(risk_filepath, "w", encoding="utf-8") as f:
                            json.dump(all_risks, f, indent=4)
                        
                        high = sum(1 for r in all_risks if r.get('risk_level') == 'HIGH')
                        med  = sum(1 for r in all_risks if r.get('risk_level') == 'MEDIUM')
                        low  = sum(1 for r in all_risks if r.get('risk_level') == 'LOW')
                        
                        summary_header.success(f"**Risk Analysis Completed** | :red[**HIGH:**] {high} | :blue[**MEDIUM:**] {med} | :green[**LOW:**] {low}")
                        st.toast(f"Risk results safely stored in {risk_filepath}")
            finally:
                st.session_state.risk_run_stage = 0 
                st.session_state.is_processing = False 
                st.rerun() 

        # --- STAGE 0: IDLE DISPLAY ---
        elif 'risk_results' in st.session_state.analysis_results and st.session_state.risk_run_stage == 0:
            display_container = master_risk_placeholder.container()
            risks = st.session_state.analysis_results['risk_results']
            high = sum(1 for r in risks if r.get('risk_level') == 'HIGH')
            med  = sum(1 for r in risks if r.get('risk_level') == 'MEDIUM')
            low  = sum(1 for r in risks if r.get('risk_level') == 'LOW')
            
            display_container.success(f"**Risk Analysis Completed** | :red[**HIGH:**] {high} | :blue[**MEDIUM:**] {med} | :green[**LOW:**] {low}")
            for risk in risks:
                render_risk_card(risk, display_container)

if __name__ == "__main__":
    main()