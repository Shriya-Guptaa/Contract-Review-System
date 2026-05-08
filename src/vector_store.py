"""
Vector Store Module
Manages FAISS vector store for document retrieval with Semantic Caching
"""

import os
import pickle
from typing import List, Dict, Optional
import numpy as np
import faiss
import streamlit as st
from sentence_transformers import SentenceTransformer


class VectorStore:
    """Manages vector storage and retrieval using FAISS"""
    
    def __init__(self, 
                 persist_directory: str = "./data/vector_store",
                 collection_name: str = "compliance_documents",
                 embedding_model: str = "all-MiniLM-L6-v2"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        os.makedirs(persist_directory, exist_ok=True)
        
        print(f"Loading embedding model: {embedding_model}")
        self.embedding_model = SentenceTransformer(embedding_model, device='cpu')
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        
        self.index = None
        self.documents = []  
        self.doc_ids = []    
        
        self._load_index()
        
        if self.index is None:
            self.index = faiss.IndexFlatL2(self.embedding_dim)
            print(f"Created new FAISS index with dimension {self.embedding_dim}")


    @st.cache_data(show_spinner=False)
    #def cached_search(_self, query: str, n_results: int = 5, filter_metadata: Optional[Dict] = None, score_threshold: float = 0.7) -> Dict:
    def cached_search(_self, query: str, n_results: int = 5, filter_metadata: Optional[Dict] = None) -> Dict:
        """
        Streamlit-native cache for FAISS results. 
        """
        #return _self.search(query, n_results, filter_metadata, score_threshold)
        return _self.search(query, n_results, filter_metadata)

    def _get_index_path(self) -> str:
        return os.path.join(self.persist_directory, f"{self.collection_name}.index")
    
    def _get_metadata_path(self) -> str:
        return os.path.join(self.persist_directory, f"{self.collection_name}.pkl")
    
    def _load_index(self):
        index_path = self._get_index_path()
        metadata_path = self._get_metadata_path()
        
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            try:
                self.index = faiss.read_index(index_path)
                with open(metadata_path, 'rb') as f:
                    data = pickle.load(f)
                    self.documents = data['documents']
                    self.doc_ids = data['doc_ids']
                print(f"Loaded existing index with {len(self.documents)} documents")
            except Exception as e:
                print(f"Error loading index: {e}")
                self.index = None
    
    def _save_index(self):
        try:
            index_path = self._get_index_path()
            metadata_path = self._get_metadata_path()
            faiss.write_index(self.index, index_path)
            with open(metadata_path, 'wb') as f:
                pickle.dump({
                    'documents': self.documents,
                    'doc_ids': self.doc_ids
                }, f)
            print(f"Saved index with {len(self.documents)} documents")
        except Exception as e:
            print(f"Error saving index: {e}")
    
    def add_documents(self, chunks: List, batch_size: int = 100) -> None:
        print(f"Adding {len(chunks)} chunks to vector store...")
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [chunk.content for chunk in batch]
            metadatas = [chunk.metadata for chunk in batch]
            ids = [f"{chunk.source}_{chunk.page_number}_{chunk.chunk_index}" for chunk in batch]
            
            embeddings = self.embedding_model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
            self.index.add(embeddings.astype('float32'))
            
            for text, metadata, doc_id in zip(texts, metadatas, ids):
                self.documents.append({'text': text, 'metadata': metadata, 'id': doc_id})
                self.doc_ids.append(doc_id)
        
        self._save_index()
    
    def search(self, query: str, n_results: int = 5, filter_metadata: Optional[Dict] = None) -> Dict:
        try:
            if self.index is None or len(self.documents) == 0:
                return {"documents": [], "metadatas": [], "distances": [], "ids": []}
            
            query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)
            distances, indices = self.index.search(query_embedding.astype('float32'), min(n_results * 2, len(self.documents)))
            
            documents, metadatas, result_distances, ids = [], [], [], []
            for dist, idx in zip(distances[0], indices[0]):
                # print(f"DEBUG: Found chunk with distance {dist}")
                if idx == -1: continue

                doc = self.documents[idx]
                if filter_metadata:
                    if not all(doc['metadata'].get(k) == v for k, v in filter_metadata.items()):
                        continue
                
                documents.append(doc['text'])
                metadatas.append(doc['metadata'])
                result_distances.append(float(dist))
                ids.append(doc['id'])
                
                if len(documents) >= n_results: break
            
            return {"documents": documents, "metadatas": metadatas, "distances": result_distances, "ids": ids}
        except Exception as e:
            print(f"Error searching documents: {e}")
            return {"documents": [], "metadatas": [], "distances": [], "ids": []}


    def collection_exists(self) -> bool:
        return os.path.exists(self._get_index_path()) and os.path.exists(self._get_metadata_path())
