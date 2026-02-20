"""
Standalone CLI script to fetch medical content from free public APIs/websites
and ingest it into the Pinecone vector store alongside the existing PDF data.

Sources:
  - MedlinePlus (NLM XML API) — consumer-friendly disease/condition summaries
  - WHO Disease Fact Sheets   — global disease burden, symptoms, prevention
  - CDC Health Topics         — US disease guidelines and health information
  - FDA DailyMed              — drug labels (indications, warnings, dosage, interactions)

Usage:
  python fetch_web_sources.py
  python fetch_web_sources.py --sources medlineplus,cdc
  python fetch_web_sources.py --sources who,dailymed --max-topics 100
"""

import argparse
import hashlib
import json
import logging
import os
import re
import time
import warnings
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone

warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ── Config ─────────────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=env_path)

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "medicore-ai")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "pritamdeka/S-PubMedBert-MS-MARCO")

CHUNK_SIZE = 1000        # Must match rag_setup.py
CHUNK_OVERLAP = 200      # Must match rag_setup.py
BATCH_SIZE = 100
REQUEST_DELAY = 1.2      # Seconds between HTTP requests (polite crawling)
MAX_RETRIES = 3
REQUEST_TIMEOUT = 20

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Medicore-AI-Bot/1.0 (Medical RAG ingestion; "
        "educational/research purpose; contact: admin@medicore.ai)"
    )
}


# ── HTTP helper ────────────────────────────────────────────────────────────────

def _get(url: str, params: Optional[dict] = None, accept_xml: bool = False) -> Optional[requests.Response]:
    """GET with retry + exponential back-off. Returns Response or None on failure."""
    headers = dict(HEADERS)
    if accept_xml:
        headers["Accept"] = "application/xml, text/xml"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 503):
                wait = 2 ** attempt
                logger.warning("Rate limited (%s). Waiting %ds…", resp.status_code, wait)
                time.sleep(wait)
            else:
                logger.warning("HTTP %s for %s", resp.status_code, url)
                return None
        except requests.RequestException as exc:
            logger.warning("Request error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(2 ** attempt)
    return None


# ── Text utilities ─────────────────────────────────────────────────────────────

def clean_text(raw: str) -> str:
    """Normalize whitespace, strip HTML entities and boilerplate."""
    text = re.sub(r"<[^>]+>", " ", raw)          # strip any residual HTML tags
    text = re.sub(r"&[a-z]+;", " ", text)          # HTML entities
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_documents(documents: List[Dict]) -> List[Dict]:
    """
    Split document texts using the same splitter config as rag_setup.py.
    Each document dict must have keys: text, source, title, url.
    Returns list of chunk dicts with added chunk_index.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = []
    for doc in documents:
        text = doc.get("text", "").strip()
        if len(text) < 50:
            continue
        parts = splitter.split_text(text)
        for idx, part in enumerate(parts):
            chunks.append({
                "text": part,
                "source": doc["source"],
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "chunk_index": idx,
            })
    return chunks


# ── Pinecone upsert ────────────────────────────────────────────────────────────

def embed_and_upsert(
    chunks: List[Dict],
    embedding_model: HuggingFaceEmbeddings,
    index,
    source_tag: str,
) -> int:
    """
    Embed chunks in batches of BATCH_SIZE and upsert to Pinecone.
    Vector ID = MD5(text) — same strategy as rag_setup.py (idempotent).
    Returns the number of vectors upserted.
    """
    total = 0
    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        try:
            vectors_raw = embedding_model.embed_documents(texts)
        except Exception as exc:
            logger.error("Embedding error: %s — skipping batch", exc)
            continue

        vectors_to_upsert = []
        for chunk, vec in zip(batch, vectors_raw):
            vid = hashlib.md5(chunk["text"].encode()).hexdigest()
            metadata = {
                "text": chunk["text"][:500],           # Pinecone metadata cap
                "source": source_tag,
                "title": chunk["title"][:200],
                "url": chunk["url"][:500],
                "chunk_id": chunk["chunk_index"],
            }
            vectors_to_upsert.append({"id": vid, "values": vec, "metadata": metadata})

        try:
            index.upsert(vectors=vectors_to_upsert)
            total += len(vectors_to_upsert)
            logger.info("  Upserted batch %d–%d (%d total so far)",
                        batch_start, batch_start + len(batch), total)
        except Exception as exc:
            logger.error("Pinecone upsert error: %s", exc)

    return total


# ── Source 1: MedlinePlus ──────────────────────────────────────────────────────

def fetch_medlineplus_topics(max_topics: int = 500) -> List[Dict]:
    """
    Fetch health topic summaries from the MedlinePlus XML search API.
    Returns list of document dicts.
    """
    logger.info("=== Fetching MedlinePlus health topics (max %d) ===", max_topics)
    docs = []
    retstart = 0
    batch = 50

    while retstart < max_topics:
        resp = _get(
            "https://wsearch.nlm.nih.gov/ws/query",
            params={
                "db": "healthTopics",
                "term": "*",
                "retmax": min(batch, max_topics - retstart),
                "retstart": retstart,
            },
            accept_xml=True,
        )
        if resp is None:
            logger.warning("MedlinePlus: no response at offset %d — stopping", retstart)
            break

        try:
            soup = BeautifulSoup(resp.content, "xml")
        except Exception:
            soup = BeautifulSoup(resp.content, "lxml")

        documents = soup.find_all("document")
        if not documents:
            break

        for doc_el in documents:
            title_el = doc_el.find("content", attrs={"name": "title"})
            full_summary_el = doc_el.find("content", attrs={"name": "FullSummary"})
            url_el = doc_el.get("url", "")

            title = clean_text(title_el.get_text()) if title_el else ""
            summary = clean_text(full_summary_el.get_text()) if full_summary_el else ""

            if summary and len(summary) > 100:
                docs.append({
                    "text": f"{title}\n\n{summary}" if title else summary,
                    "title": title,
                    "url": url_el,
                    "source": "medlineplus",
                })

        retstart += len(documents)
        logger.info("  MedlinePlus: fetched %d topics so far", retstart)

        if len(documents) < batch:
            break
        time.sleep(REQUEST_DELAY)

    logger.info("MedlinePlus: %d documents fetched", len(docs))
    return docs


# ── Source 2: WHO Fact Sheets ──────────────────────────────────────────────────

_WHO_INDEX = "https://www.who.int/news-room/fact-sheets"

def _fetch_who_fact_sheet(url: str) -> Optional[str]:
    """Fetch a single WHO fact sheet page and extract body text."""
    resp = _get(url)
    if resp is None:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    # WHO pages keep article body in <div class="sf-detail-body-wrapper">
    body = soup.find("div", class_=re.compile(r"sf-detail-body", re.I))
    if not body:
        body = soup.find("article") or soup.find("main")
    if body is None:
        return None
    # Remove navigation, scripts, styles
    for tag in body.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    return clean_text(body.get_text(separator=" "))


def fetch_who_fact_sheets(max_sheets: int = 100) -> List[Dict]:
    """
    Scrape WHO disease fact sheet index and individual pages.
    Returns list of document dicts.
    """
    logger.info("=== Fetching WHO fact sheets (max %d) ===", max_sheets)
    docs = []

    resp = _get(_WHO_INDEX)
    if resp is None:
        logger.warning("WHO: Could not fetch index page")
        return docs

    soup = BeautifulSoup(resp.text, "html.parser")
    # Links to individual fact sheets
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/fact-sheets/detail/" in href:
            full_url = href if href.startswith("http") else f"https://www.who.int{href}"
            if full_url not in links:
                links.append(full_url)

    logger.info("  WHO: found %d fact sheet links", len(links))

    for url in links[:max_sheets]:
        time.sleep(REQUEST_DELAY)
        title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
        text = _fetch_who_fact_sheet(url)
        if text and len(text) > 200:
            docs.append({"text": text, "title": title, "url": url, "source": "who"})

    logger.info("WHO: %d fact sheets fetched", len(docs))
    return docs


# ── Source 3: CDC Health Topics ────────────────────────────────────────────────

def _fetch_cdc_topic_text(url: str) -> Optional[str]:
    """Fetch a CDC health topic page and extract main text content."""
    resp = _get(url)
    if resp is None:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("div", id="content") or soup.find("div", class_=re.compile(r"content", re.I))
    if main is None:
        return None
    return clean_text(main.get_text(separator=" "))


def fetch_cdc_health_topics(max_topics: int = 150) -> List[Dict]:
    """
    Scrape the CDC A-Z health topics index and individual topic pages.
    Returns list of document dicts.
    """
    logger.info("=== Fetching CDC health topics (max %d) ===", max_topics)
    docs = []
    collected_urls = []

    for letter in "abcdefghijklmnopqrstuvwxyz":
        index_url = f"https://www.cdc.gov/az/{letter}.html"
        resp = _get(index_url)
        if resp is None:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/") and not href.startswith("//"):
                full_url = f"https://www.cdc.gov{href}"
            elif href.startswith("https://www.cdc.gov"):
                full_url = href
            else:
                continue
            if full_url not in collected_urls:
                collected_urls.append(full_url)
        time.sleep(REQUEST_DELAY * 0.5)

        if len(collected_urls) >= max_topics * 3:
            break

    logger.info("  CDC: found %d topic links", len(collected_urls))

    for url in collected_urls[:max_topics]:
        time.sleep(REQUEST_DELAY)
        title = url.rstrip("/").split("/")[-1].replace("-", " ").replace(".html", "").title()
        text = _fetch_cdc_topic_text(url)
        if text and len(text) > 200:
            docs.append({"text": text, "title": title, "url": url, "source": "cdc"})

    logger.info("CDC: %d topics fetched", len(docs))
    return docs


# ── Source 4: FDA DailyMed ────────────────────────────────────────────────────

# Common drug categories to search for
_DAILYMED_SEARCH_TERMS = [
    "metformin", "lisinopril", "atorvastatin", "amlodipine", "omeprazole",
    "metoprolol", "albuterol", "losartan", "levothyroxine", "simvastatin",
    "gabapentin", "hydrochlorothiazide", "furosemide", "sertraline", "amoxicillin",
    "prednisone", "warfarin", "aspirin", "ibuprofen", "acetaminophen",
    "azithromycin", "ciprofloxacin", "doxycycline", "cephalexin", "clindamycin",
    "metronidazole", "trimethoprim", "fluconazole", "acyclovir", "oseltamivir",
    "insulin", "glipizide", "glimepiride", "sitagliptin", "empagliflozin",
    "amlodipine", "diltiazem", "verapamil", "digoxin", "spironolactone",
    "carvedilol", "atenolol", "bisoprolol", "ramipril", "enalapril",
    "clopidogrel", "apixaban", "rivaroxaban", "dabigatran", "heparin",
    "ondansetron", "metoclopramide", "ranitidine", "pantoprazole", "esomeprazole",
    "fluoxetine", "escitalopram", "bupropion", "venlafaxine", "duloxetine",
    "lorazepam", "alprazolam", "diazepam", "zolpidem", "quetiapine",
    "risperidone", "aripiprazole", "haloperidol", "lithium", "valproate",
    "levetiracetam", "phenytoin", "carbamazepine", "lamotrigine", "topiramate",
    "morphine", "oxycodone", "tramadol", "codeine", "fentanyl",
    "prednisolone", "dexamethasone", "hydrocortisone", "methylprednisolone",
    "montelukast", "fluticasone", "budesonide", "tiotropium", "salmeterol",
]

_SECTIONS_OF_INTEREST = {
    "indications and usage", "dosage and administration",
    "warnings and precautions", "adverse reactions",
    "drug interactions", "contraindications",
    "mechanism of action", "pharmacokinetics",
}


def _parse_spl_xml(xml_bytes: bytes, drug_name: str, url: str) -> Optional[Dict]:
    """Extract key clinical sections from a DailyMed SPL XML document."""
    try:
        soup = BeautifulSoup(xml_bytes, "xml")
    except Exception:
        soup = BeautifulSoup(xml_bytes, "lxml")

    sections = []
    for section in soup.find_all("section"):
        title_el = section.find("title")
        title_text = title_el.get_text(strip=True).lower() if title_el else ""
        if any(kw in title_text for kw in _SECTIONS_OF_INTEREST):
            body = section.get_text(separator=" ", strip=True)
            body = clean_text(body)
            if len(body) > 50:
                sections.append(f"[{title_text.title()}]\n{body}")

    if not sections:
        return None

    combined = "\n\n".join(sections)
    return {
        "text": f"Drug: {drug_name}\n\n{combined}",
        "title": f"{drug_name.title()} Drug Label",
        "url": url,
        "source": "dailymed",
    }


def fetch_dailymed_drug_labels(drug_terms: Optional[List[str]] = None) -> List[Dict]:
    """
    Fetch FDA DailyMed drug label SPL documents for a list of drug names.
    Returns list of document dicts.
    """
    if drug_terms is None:
        drug_terms = _DAILYMED_SEARCH_TERMS

    logger.info("=== Fetching DailyMed drug labels (%d drugs) ===", len(drug_terms))
    docs = []

    for drug in drug_terms:
        time.sleep(REQUEST_DELAY)
        search_resp = _get(
            "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json",
            params={"drug_name": drug, "pagesize": 1},
        )
        if search_resp is None:
            continue

        try:
            data = search_resp.json()
            spls = data.get("data", [])
        except ValueError:
            continue

        if not spls:
            continue

        set_id = spls[0].get("setid")
        if not set_id:
            continue

        time.sleep(REQUEST_DELAY)
        xml_resp = _get(
            f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{set_id}.xml",
            accept_xml=True,
        )
        if xml_resp is None:
            continue

        label_url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}"
        doc = _parse_spl_xml(xml_resp.content, drug, label_url)
        if doc:
            docs.append(doc)
            logger.info("  DailyMed: fetched label for '%s'", drug)

    logger.info("DailyMed: %d drug labels fetched", len(docs))
    return docs


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest web medical sources into Pinecone")
    parser.add_argument(
        "--sources",
        default="medlineplus,who,cdc,dailymed",
        help="Comma-separated list of sources to ingest (default: all)",
    )
    parser.add_argument(
        "--max-topics",
        type=int,
        default=300,
        help="Max topics/pages per source (default: 300)",
    )
    args = parser.parse_args()
    selected = {s.strip().lower() for s in args.sources.split(",")}

    if not PINECONE_API_KEY:
        logger.error("PINECONE_API_KEY not found. Check backend/.env")
        return

    # ── Initialize Pinecone
    logger.info("Connecting to Pinecone index '%s'…", PINECONE_INDEX_NAME)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    # ── Load embedding model (same as rag_setup.py)
    logger.info("Loading embedding model '%s'…", EMBEDDING_MODEL)
    embedding_model = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
    )
    logger.info("Embedding model ready.")

    grand_total = 0

    # ── MedlinePlus
    if "medlineplus" in selected:
        try:
            docs = fetch_medlineplus_topics(max_topics=args.max_topics)
            chunks = chunk_documents(docs)
            logger.info("MedlinePlus: %d chunks to upsert", len(chunks))
            n = embed_and_upsert(chunks, embedding_model, index, "medlineplus")
            grand_total += n
            logger.info("MedlinePlus: %d vectors upserted", n)
        except Exception as exc:
            logger.error("MedlinePlus pipeline failed: %s", exc)

    # ── WHO
    if "who" in selected:
        try:
            docs = fetch_who_fact_sheets(max_sheets=min(args.max_topics, 100))
            chunks = chunk_documents(docs)
            logger.info("WHO: %d chunks to upsert", len(chunks))
            n = embed_and_upsert(chunks, embedding_model, index, "who")
            grand_total += n
            logger.info("WHO: %d vectors upserted", n)
        except Exception as exc:
            logger.error("WHO pipeline failed: %s", exc)

    # ── CDC
    if "cdc" in selected:
        try:
            docs = fetch_cdc_health_topics(max_topics=min(args.max_topics, 150))
            chunks = chunk_documents(docs)
            logger.info("CDC: %d chunks to upsert", len(chunks))
            n = embed_and_upsert(chunks, embedding_model, index, "cdc")
            grand_total += n
            logger.info("CDC: %d vectors upserted", n)
        except Exception as exc:
            logger.error("CDC pipeline failed: %s", exc)

    # ── DailyMed
    if "dailymed" in selected:
        try:
            docs = fetch_dailymed_drug_labels()
            chunks = chunk_documents(docs)
            logger.info("DailyMed: %d chunks to upsert", len(chunks))
            n = embed_and_upsert(chunks, embedding_model, index, "dailymed")
            grand_total += n
            logger.info("DailyMed: %d vectors upserted", n)
        except Exception as exc:
            logger.error("DailyMed pipeline failed: %s", exc)

    logger.info("=== Ingestion complete. Total vectors upserted: %d ===", grand_total)


if __name__ == "__main__":
    main()
