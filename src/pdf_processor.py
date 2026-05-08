import io
import fitz  # PyMuPDF
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class DocumentChunk:
    """Represents a chunk of document with metadata"""
    content: str
    source: io.BytesIO
    page_number: int
    chunk_index: int
    metadata: Dict

class PDFProcessor:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text_from_uploaded_pdf(self, uploaded_file: io.BytesIO) -> Dict[int, str]:
        pages_text = {}
        try:
            uploaded_file.seek(0)
            # Read bytes into fitz
            doc = fitz.open(stream=uploaded_file, filetype="pdf")
            for page_num, page in enumerate(doc, start=1):
                # get_text("words") returns a list of tuples: 
                # (x0, y0, x1, y1, "word", block_no, line_no, word_no)
                words = page.get_text("words")
                text = " ".join([w[4] for w in words])
                if text:
                    pages_text[page_num] = text
            doc.close()
        except Exception as e:
            print(f" Error: {str(e)}")
        return pages_text

    def process_uploaded_pdf(self, uploaded_file: io.BytesIO, source_name: str) -> List[DocumentChunk]:
        """
        Used for Vector Store ingestion. Processes PDF into clean, spaced chunks.
        """
        all_chunks = []
        uploaded_file.seek(0)
        
        doc = fitz.open(stream=uploaded_file, filetype="pdf")
        for i, page in enumerate(doc):
            page_num = i + 1
            
            # Extract words and map to the dictionary format expected by the helper
            raw_words = page.get_text("words")
            words = [
                {
                    "x0": w[0],
                    "top": w[1],
                    "x1": w[2],
                    "bottom": w[3],
                    "text": w[4]
                }
                for w in raw_words
            ]
            
            if words:
                page_chunks = self._create_chunks_with_coords(
                    words, uploaded_file, page_num, source_name
                )
                all_chunks.extend(page_chunks)
        doc.close()
        return all_chunks

    def _create_chunks_with_coords(self, words: List[Dict], source, page_num: int, filename: str) -> List[DocumentChunk]:
        """
        Groups words into chunks and captures their bounding box.
        FIXED: Explicitly joins words with spaces to fix 'mashed' text.
        """
        chunks = []
        current_chunk_words = []
        current_length = 0
        chunk_index = 0
        
        i = 0
        while i < len(words):
            word = words[i]
            word_len = len(word['text']) + 1 
            
            current_chunk_words.append(word)
            current_length += word_len
            
            if current_length >= self.chunk_size or i == len(words) - 1:
                # JOINING WITH SPACES: Prevents text clumping
                chunk_text = " ".join([w['text'] for w in current_chunk_words])
                
                # Bounding Box Calculation
                x0 = min([w['x0'] for w in current_chunk_words])
                top = min([w['top'] for w in current_chunk_words])
                x1 = max([w['x1'] for w in current_chunk_words])
                bottom = max([w['bottom'] for w in current_chunk_words])
                
                chunk = DocumentChunk(
                    content=chunk_text,
                    source=source,
                    page_number=page_num,
                    chunk_index=chunk_index,
                    metadata={
                        "filename": filename,
                        "page": page_num,
                        "chunk": chunk_index,
                        "coordinates": {
                            "x0": float(x0), "top": float(top), 
                            "x1": float(x1), "bottom": float(bottom),
                            "width": float(x1 - x0), "height": float(bottom - top)
                        }
                    }
                )
                
                if chunk.content.strip():
                    chunks.append(chunk)
                    chunk_index += 1
                
                # Overlap logic
                overlap_len = 0
                overlap_words_count = 0
                for w in reversed(current_chunk_words):
                    overlap_len += len(w['text']) + 1
                    overlap_words_count += 1
                    if overlap_len >= self.chunk_overlap:
                        break
                
                if i < len(words) - 1:
                    i -= (overlap_words_count - 1) 
                
                current_chunk_words = []
                current_length = 0
            i += 1
        return chunks
