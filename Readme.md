# Contract Review System

## Overview

Contract Review System is a Retrieval-Augmented Generation (RAG)-based legal document analysis platform designed to automate contract understanding, compliance checking, clause summarization, and risk assessment.

The system processes uploaded PDF contracts, retrieves relevant clauses using semantic search with FAISS embeddings, and uses a fine-tuned Mistral Large Language Model (LLM) to generate structured outputs.

The project was developed as part of my major project focusing on explainable and modular AI-assisted contract analysis.

---

# Features

## 1. Contract Summarization

* Extracts key contract sections
* Generates concise clause summaries
* Uses retrieval-based contextual summarization

## 2. Compliance Checking

* Rule-based compliance evaluation
* Semantic retrieval using FAISS
* Multi-stage keyword validation pipeline
* Evidence-based clause extraction

## 3. Risk Analysis

* Business risk assessment based on compliance results
* Generates:

  * Risk level
  * Business impact
  * Recommendations

## 4. PDF Report Generation

* Generates structured downloadable PDF reports
* Includes:

  * Clause summaries
  * Compliance results
  * Risk analysis

---

# System Architecture

```text
User Uploads PDF
        ↓
PDF Processing & Chunking
        ↓
Embedding Generation (MiniLM)
        ↓
FAISS Vector Storage
        ↓
Semantic Retrieval
        ↓
Fine-Tuned Mistral LLM
        ↓
Summary / Compliance / Risk Analysis
        ↓
PDF Report Generation
```

---

# Tech Stack

| Component          | Technology                |
| ------------------ | ------------------------- |
| Frontend           | Streamlit                 |
| LLM                | Fine-Tuned Mistral 7B     |
| Embeddings         | all-MiniLM-L6-v2          |
| Vector Database    | FAISS                     |
| PDF Processing     | PyMuPDF                   |
| Report Generation  | ReportLab                 |
| Inference Hosting  | Google Colab + Ngrok      |
| Training Framework | Hugging Face + LoRA/QLoRA |

---

# Project Structure

```text
Contract-Review-System/
│
├── app.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
│
└── src/
    │
    ├── compliance_checker.py
    ├── key_clause_summarizer.py
    ├── llm_client.py
    ├── pdf_processor.py
    ├── report_generator.py
    ├── risk_and_reco.py
    └── vector_store.py

---

# Excluded Folders

The following folders are excluded from the repository:

| Folder        | Reason                                         |
| ------------- | ---------------------------------------------- |
| `models/`     | Large GGUF model files                         |
| `data/`       | Generated vector indexes and metadata          |
| `logs/`       | Runtime logs                                   |
| `config/`     | Environment-specific configuration             |
| `trainingV2/` | Training datasets and generated training files |

---

# Training Process (Summary)

The LLM used in this project was fine-tuned using LoRA/QLoRA techniques on legal-domain datasets.

## Datasets Used

* CUAD (Contract Understanding Atticus Dataset)
* ACORD Dataset
* Custom compliance-rule datasets

## Training Objectives

* Clause extraction
* Compliance-oriented reasoning
* Legal summarization
* Risk-related analysis

## Training Stack

* Hugging Face Transformers
* Unsloth
* PEFT (LoRA/QLoRA)
* GGUF conversion for inference

The final model is served remotely through Google Colab and exposed to the application using Ngrok.

---

# Retrieval Pipeline

The system follows a Retrieval-Augmented Generation (RAG) architecture:

1. PDF text extraction
2. Chunk creation with overlap
3. Embedding generation using MiniLM
4. Vector storage in FAISS
5. Semantic retrieval using rule-based queries
6. LLM-based analysis on retrieved chunks

---

# Compliance Checking Workflow

```text
Rule Selection
      ↓
Query Generation
      ↓
FAISS Retrieval
      ↓
Keyword Validation
      ↓
LLM Clause Extraction
      ↓
Evidence Verification
      ↓
COMPLIANT / NON-COMPLIANT
```

The compliance system uses a hybrid retrieval-validation approach combining semantic retrieval with strict keyword-based verification.

---

# Installation

## 1. Clone Repository

```bash
git clone <repository-url>
cd <repository-name>
```

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Running the Application

## Start Streamlit App

```bash
streamlit run app.py
```

---

# Remote LLM Setup

The application expects a running remote inference server exposed through Ngrok.

Update the remote endpoint inside:

```text
config/model_config.py
```

---

# Key Research Contributions

* Hybrid RAG-based legal analysis pipeline
* Rule-driven compliance evaluation
* Multi-stage evidence verification
* Modular explainable architecture
* Integration of retrieval and legal reasoning workflows

---

# Limitations

* Compliance logic is primarily keyword-guided
* Requires active remote inference server
* Performance depends on retrieval quality
* Does not replace professional legal review

---

# Future Improvements

* Full logical compliance reasoning
* Multi-contract comparison
* Clause highlighting in PDFs
* Persistent analysis caching
* Improved legal reasoning datasets
* Multi-agent legal workflows

---

# Disclaimer

This project is intended for research and educational purposes only. It does not provide legal advice. It is under MIT License
