import os
import hashlib
import warnings
from typing import List, Generator
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
import time
import json

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Load .env from parent directory (Medicore folder)
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
print(f"Looking for .env file at: {os.path.abspath(env_path)}")
loaded = load_dotenv(dotenv_path=env_path)
print(f".env file loaded: {loaded}\n")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "medicore-ai")
DATA_PATH = "data/pdfs/"
CHECKPOINT_FILE = "ingestion_checkpoint.json"

# Debug output
if not PINECONE_API_KEY:
    print("⚠ WARNING: PINECONE_API_KEY not found in environment!")
    print(f"Checked .env path: {os.path.abspath(env_path)}")
    print("Please ensure your .env file contains: PINECONE_API_KEY=your-key-here\n")
else:
    print(f"✓ API Key loaded (length: {len(PINECONE_API_KEY)})\n")

def load_pdf_files_generator(data_path: str) -> Generator[Document, None, None]:
    """Memory-efficient PDF loading using generator pattern"""
    pdf_files = [f for f in os.listdir(data_path) if f.endswith('.pdf')]
    
    print(f"Found {len(pdf_files)} PDF files")
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(data_path, pdf_file)
        print(f"  Processing: {pdf_file}")
        
        loader = PyMuPDFLoader(pdf_path)
        docs = loader.load()
        
        # Add filename metadata and yield immediately
        for doc in docs:
            doc.metadata['filename'] = pdf_file
            if 'page' not in doc.metadata:
                doc.metadata['page'] = 0
            yield doc
        
        print(f"    Loaded {len(docs)} pages")

def deduplicate_documents(documents: List[Document]) -> List[Document]:
    """Deduplicate at document level BEFORE chunking (big efficiency win)"""
    seen_hashes = set()
    unique_docs = []
    
    for doc in documents:
        content_hash = hashlib.md5(doc.page_content.encode()).hexdigest()
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            unique_docs.append(doc)
    
    duplicates_removed = len(documents) - len(unique_docs)
    if duplicates_removed > 0:
        print(f"Removed {duplicates_removed} duplicate pages/documents")
    
    return unique_docs

def create_chunks(extracted_data: List[Document]) -> List[Document]:
    """Create optimized chunks for medical/technical content"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    text_chunks = text_splitter.split_documents(extracted_data)
    
    # Add chunk metadata
    for idx, chunk in enumerate(text_chunks):
        chunk.metadata['chunk_id'] = idx
    
    return text_chunks

def initialize_pinecone_index(pc: Pinecone, index_name: str, dimension: int = 768):
    """Initialize Pinecone index with dimension validation"""
    existing_indexes = [index.name for index in pc.list_indexes()]
    
    if index_name in existing_indexes:
        # Check if existing index has correct dimension
        index_info = pc.describe_index(index_name)
        existing_dimension = index_info.dimension
        
        if existing_dimension != dimension:
            print(f"⚠ WARNING: Existing index has dimension {existing_dimension}, but model produces {dimension}")
            print(f"Deleting existing index '{index_name}' to recreate with correct dimension...")
            pc.delete_index(index_name)
            print("Index deleted. Creating new index...")
            time.sleep(5)  # Wait for deletion to complete
            
            pc.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            
            print("Waiting for index to be ready...")
            while not pc.describe_index(index_name).status['ready']:
                time.sleep(1)
            print("Index is ready!")
        else:
            print(f"Using existing Pinecone index: {index_name} (dimension: {existing_dimension})")
    else:
        print(f"Creating new Pinecone index: {index_name} (dimension: {dimension})")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        
        print("Waiting for index to be ready...")
        while not pc.describe_index(index_name).status['ready']:
            time.sleep(1)
        print("Index is ready!")

def batch_upsert_with_checkpoint(chunks: List[Document], embedding_model, pc: Pinecone, 
                                  index_name: str, batch_size: int = 100):
    """
    Advanced: Manual embedding + batch upsert with checkpointing
    Uses content-hash based vector IDs for stable, collision-free re-ingestion
    """
    index = pc.Index(index_name)
    
    # Load checkpoint if exists
    start_idx = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
            start_idx = checkpoint.get('last_processed_idx', 0)
            print(f"Resuming from checkpoint: {start_idx}/{len(chunks)}")
    
    total_chunks = len(chunks)
    print(f"Processing {total_chunks - start_idx} chunks in batches of {batch_size}...")
    
    for i in range(start_idx, total_chunks, batch_size):
        batch = chunks[i:i + batch_size]
        
        # Extract texts and generate embeddings
        texts = [chunk.page_content for chunk in batch]
        embeddings = embedding_model.embed_documents(texts)
        
        # Prepare vectors for Pinecone
        vectors = []
        for chunk, embedding in zip(batch, embeddings):
            # Use content hash as vector ID for stable, deterministic IDs
            # This enables safe re-ingestion and natural deduplication
            vector_id = hashlib.md5(chunk.page_content.encode()).hexdigest()
            
            # Smart metadata: store only essential fields
            # Text preview kept minimal (Pinecone has metadata size limits)
            metadata = {
                'text': chunk.page_content[:500],  # Reduced from 1000 for efficiency
                'filename': chunk.metadata.get('filename', 'unknown'),
                'page': chunk.metadata.get('page', 0),
                'chunk_id': chunk.metadata.get('chunk_id', 0)
            }
            vectors.append((vector_id, embedding, metadata))
        
        # Upsert batch (content-hash IDs mean duplicates auto-update, not duplicate)
        index.upsert(vectors=vectors)
        
        # Save checkpoint
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({'last_processed_idx': i + len(batch)}, f)
        
        # Progress update
        progress = min(i + batch_size, total_chunks)
        percent = (progress / total_chunks) * 100
        print(f"  Progress: {progress}/{total_chunks} ({percent:.1f}%)")
    
    # Clean up checkpoint file on completion
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
    
    print("✓ All vectors uploaded successfully!")

def main():
    try:
        # Step 1: Load PDFs using generator (memory efficient)
        print("=" * 60)
        print("STEP 1: Loading PDF files...")
        print("=" * 60)
        
        # Convert generator to list (we need to dedupe, so must materialize)
        # For truly massive datasets, you'd chunk this differently
        documents = list(load_pdf_files_generator(data_path=DATA_PATH))
        print(f"✓ Loaded {len(documents)} pages from PDF files\n")
        
        if len(documents) == 0:
            print(f"⚠ No PDF files found in {DATA_PATH}")
            return
        
        # Step 2: Deduplicate at document level (BEFORE chunking)
        print("=" * 60)
        print("STEP 2: Deduplicating documents (before chunking)...")
        print("=" * 60)
        unique_documents = deduplicate_documents(documents)
        print(f"✓ {len(unique_documents)} unique documents remaining\n")
        
        # Free memory
        documents = None
        
        # Step 3: Create Chunks
        print("=" * 60)
        print("STEP 3: Creating text chunks...")
        print("=" * 60)
        text_chunks = create_chunks(extracted_data=unique_documents)
        print(f"✓ Created {len(text_chunks)} text chunks\n")
        
        # Free memory
        unique_documents = None
        
        # Step 4: Initialize Pinecone
        print("=" * 60)
        print("STEP 4: Initializing Pinecone...")
        print("=" * 60)
        pc = Pinecone(api_key=PINECONE_API_KEY)
        initialize_pinecone_index(pc, PINECONE_INDEX_NAME, dimension=768)
        print()
        
        # Step 5: Create Medical Domain Embeddings
        print("=" * 60)
        print("STEP 5: Loading embedding model...")
        print("=" * 60)
        print("Loading PubMedBERT model (optimized for medical/biomedical text)...")
        
        embedding_model = HuggingFaceEmbeddings(
            model_name="pritamdeka/S-PubMedBert-MS-MARCO",
            model_kwargs={'device': 'cpu'},  # Change to 'cuda' if GPU available
            encode_kwargs={
                'normalize_embeddings': True,
                'batch_size': 64  # Increased from 32 for better CPU utilization
            }
        )
        print("✓ Embedding model loaded successfully\n")
        
        # Step 6: Batch upsert with checkpointing
        print("=" * 60)
        print("STEP 6: Creating embeddings and uploading to Pinecone...")
        print("=" * 60)
        print("Using batch upsert with checkpoint support...")
        print("(If interrupted, will resume from last checkpoint)\n")
        
        start_time = time.time()
        batch_upsert_with_checkpoint(
            chunks=text_chunks,
            embedding_model=embedding_model,
            pc=pc,
            index_name=PINECONE_INDEX_NAME,
            batch_size=100
        )
        elapsed = time.time() - start_time
        print(f"\n✓ Upload completed in {elapsed/60:.1f} minutes")
        
        # Summary
        print("\n" + "=" * 60)
        print("✓ SUCCESS! Vector store created successfully!")
        print("=" * 60)
        print(f"Index Name: {PINECONE_INDEX_NAME}")
        print(f"Total Vectors: {len(text_chunks)}")
        print(f"Embedding Model: PubMedBERT")
        print(f"Dimension: 768")
        print(f"Metric: Cosine similarity")
        print("\n📊 Optimizations applied:")
        print("  ✓ Page-level deduplication (before chunking)")
        print("  ✓ Increased embedding batch size (64)")
        print("  ✓ Checkpoint-based uploads (resumable)")
        print("  ✓ Content-hash vector IDs (safe re-ingestion)")
        print("  ✓ Manual batch upserts for better control")
        print("\n💡 Re-ingestion safe: Identical content = same vector ID")
        print("🚀 Ready for retrieval queries!")
        
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()