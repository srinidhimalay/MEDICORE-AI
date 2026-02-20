"""
Live context enrichment layer.
Called at query time to supplement static Pinecone RAG with real-time medical data.

Sources:
  - PubMed E-utilities : recent research abstracts (up to 3)
  - RxNorm API         : drug interaction warnings (when ≥2 drug names detected)
  - OpenFDA API        : top adverse events for detected drug (when drug detected)

All calls run concurrently with a hard 2.5-second total timeout.
Failures are silently swallowed — the main response is never blocked.
"""

import asyncio
import logging
import re
import urllib.parse
from typing import List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
LIVE_CONTEXT_TIMEOUT = 2.5     # Hard ceiling in seconds for all live calls
MAX_ABSTRACTS = 3              # PubMed: max articles to fetch
MAX_CONTEXT_CHARS = 2000       # Total chars appended to generate_response context
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=LIVE_CONTEXT_TIMEOUT)

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RXNORM_INTERACTION = "https://rxnav.nlm.nih.gov/REST/interaction/list.json"
OPENFDA_EVENTS = "https://api.fda.gov/drug/event.json"

# Common drug suffixes used for extraction heuristic
_DRUG_SUFFIXES = (
    "mab", "pril", "olol", "sartan", "statin", "mycin", "azole",
    "cillin", "cycline", "oxacin", "prazole", "azepam", "dipine",
    "afil", "tinib", "zumab", "umab", "nib", "vir", "ide", "ine",
    "imod", "fiban", "setron", "parin", "platin", "taxel",
)

# 200 commonly prescribed drug names for fast lookup
_KNOWN_DRUGS = {
    "metformin", "lisinopril", "atorvastatin", "amlodipine", "omeprazole",
    "metoprolol", "albuterol", "losartan", "levothyroxine", "simvastatin",
    "gabapentin", "hydrochlorothiazide", "furosemide", "sertraline", "amoxicillin",
    "prednisone", "warfarin", "aspirin", "ibuprofen", "acetaminophen",
    "azithromycin", "ciprofloxacin", "doxycycline", "cephalexin", "clindamycin",
    "metronidazole", "trimethoprim", "fluconazole", "acyclovir", "oseltamivir",
    "insulin", "glipizide", "glimepiride", "sitagliptin", "empagliflozin",
    "diltiazem", "verapamil", "digoxin", "spironolactone", "carvedilol",
    "atenolol", "bisoprolol", "ramipril", "enalapril", "clopidogrel",
    "apixaban", "rivaroxaban", "dabigatran", "heparin", "ondansetron",
    "metoclopramide", "ranitidine", "pantoprazole", "esomeprazole",
    "fluoxetine", "escitalopram", "bupropion", "venlafaxine", "duloxetine",
    "lorazepam", "alprazolam", "diazepam", "zolpidem", "quetiapine",
    "risperidone", "aripiprazole", "haloperidol", "lithium", "valproate",
    "levetiracetam", "phenytoin", "carbamazepine", "lamotrigine", "topiramate",
    "morphine", "oxycodone", "tramadol", "codeine", "fentanyl",
    "prednisolone", "dexamethasone", "hydrocortisone", "methylprednisolone",
    "montelukast", "fluticasone", "budesonide", "tiotropium", "salmeterol",
    "methotrexate", "hydroxychloroquine", "sulfasalazine", "adalimumab",
    "infliximab", "etanercept", "rituximab", "trastuzumab", "bevacizumab",
    "tamoxifen", "anastrozole", "letrozole", "exemestane", "imatinib",
    "erlotinib", "gefitinib", "sorafenib", "sunitinib", "ibrutinib",
    "sildenafil", "tadalafil", "vardenafil", "finasteride", "dutasteride",
    "alendronate", "risedronate", "denosumab", "teriparatide",
    "liraglutide", "semaglutide", "dulaglutide", "exenatide", "insulin glargine",
    "canagliflozin", "dapagliflozin", "pioglitazone", "rosiglitazone",
    "allopurinol", "colchicine", "febuxostat",
    "azathioprine", "mycophenolate", "tacrolimus", "cyclosporine",
    "amiodarone", "flecainide", "sotalol", "propafenone",
    "nitroglycerine", "isosorbide", "ranolazine",
    "clonidine", "doxazosin", "terazosin", "prazosin",
    "ezetimibe", "gemfibrozil", "fenofibrate", "niacin", "omega-3",
    "cholestyramine", "colesevelam",
    "baclofen", "tizanidine", "cyclobenzaprine", "methocarbamol",
    "donepezil", "memantine", "rivastigmine", "galantamine",
    "sumatriptan", "rizatriptan", "topiramate",
    "hydroxyzine", "cetirizine", "loratadine", "fexofenadine", "diphenhydramine",
    "ranitidine", "famotidine", "cimetidine", "sucralfate",
    "lactulose", "polyethylene glycol", "bisacodyl", "senna",
    "mesalamine", "sulfasalazine", "balsalazide",
    "ribavirin", "interferon", "entecavir", "tenofovir",
    "atazanavir", "lopinavir", "ritonavir", "efavirenz",
    "isoniazid", "rifampin", "pyrazinamide", "ethambutol",
    "chloroquine", "artemether", "lumefantrine", "mefloquine",
    "ivermectin", "albendazole", "mebendazole", "praziquantel",
    "vancomycin", "linezolid", "daptomycin", "tigecycline",
    "meropenem", "imipenem", "ertapenem", "piperacillin",
    "amphotericin", "voriconazole", "itraconazole", "caspofungin",
}


# ── Drug extraction ────────────────────────────────────────────────────────────

def extract_drug_names(query: str) -> List[str]:
    """
    Extract potential drug names from a query string.
    Uses two strategies:
    1. Direct lookup against a set of 200+ known drug names
    2. Regex heuristic for words ending in common drug suffixes
    Returns up to 5 unique candidates.
    """
    found = []
    words = re.findall(r"\b[a-zA-Z]{4,}\b", query.lower())

    for word in words:
        if word in _KNOWN_DRUGS and word not in found:
            found.append(word)
        elif any(word.endswith(suffix) for suffix in _DRUG_SUFFIXES) and word not in found:
            found.append(word)

    return found[:5]


# ── PubMed ─────────────────────────────────────────────────────────────────────

async def fetch_pubmed_abstracts(query: str, session: aiohttp.ClientSession) -> str:
    """
    Search PubMed for relevant abstracts using E-utilities.
    Returns formatted string or "" on error/timeout.
    """
    try:
        # Step 1: eSearch — get PMIDs
        esearch_params = {
            "db": "pubmed",
            "term": query,
            "retmax": MAX_ABSTRACTS,
            "sort": "relevance",
            "retmode": "json",
        }
        async with session.get(PUBMED_ESEARCH, params=esearch_params) as resp:
            if resp.status != 200:
                return ""
            data = await resp.json()

        pmids = data.get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return ""

        # Step 2: eFetch — get abstracts
        efetch_params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "text",
        }
        async with session.get(PUBMED_EFETCH, params=efetch_params) as resp:
            if resp.status != 200:
                return ""
            text = await resp.text()

        if not text.strip():
            return ""

        # Trim to reasonable length
        trimmed = text.strip()[:1200]
        return f"Recent PubMed Evidence:\n{trimmed}"

    except Exception as exc:
        logger.debug("PubMed fetch error: %s", exc)
        return ""


# ── RxNorm Drug Interactions ───────────────────────────────────────────────────

async def fetch_drug_interactions(drug_names: List[str], session: aiohttp.ClientSession) -> str:
    """
    Query RxNorm for drug-drug interactions between detected drug names.
    Returns formatted string or "" if <2 drugs or API error.
    """
    if len(drug_names) < 2:
        return ""

    try:
        params = {"names": " ".join(drug_names[:4])}
        async with session.get(RXNORM_INTERACTION, params=params) as resp:
            if resp.status != 200:
                return ""
            data = await resp.json()

        interactions = []
        full_ixns = data.get("fullInteractionTypeGroup", [])
        for group in full_ixns:
            for ixn_type in group.get("fullInteractionType", []):
                for pair in ixn_type.get("interactionPair", []):
                    desc = pair.get("description", "")
                    severity = pair.get("severity", "")
                    if desc:
                        interactions.append(
                            f"• [{severity}] {desc}" if severity else f"• {desc}"
                        )

        if not interactions:
            return ""

        result = "Drug Interaction Alerts:\n" + "\n".join(interactions[:3])
        return result[:600]

    except Exception as exc:
        logger.debug("RxNorm fetch error: %s", exc)
        return ""


# ── OpenFDA Adverse Events ─────────────────────────────────────────────────────

async def fetch_fda_adverse_events(drug_name: str, session: aiohttp.ClientSession) -> str:
    """
    Query OpenFDA for the top adverse reactions reported for a drug.
    Returns formatted string or "" on error/429/no data.
    """
    if not drug_name:
        return ""

    try:
        params = {
            "search": f"patient.drug.medicinalproduct:{drug_name}",
            "count": "patient.reaction.reactionmeddrapt.exact",
            "limit": "5",
        }
        async with session.get(OPENFDA_EVENTS, params=params) as resp:
            if resp.status == 429:
                logger.debug("OpenFDA rate-limited")
                return ""
            if resp.status != 200:
                return ""
            data = await resp.json()

        results = data.get("results", [])
        if not results:
            return ""

        reactions = [r["term"].lower() for r in results if r.get("term")]
        if not reactions:
            return ""

        return (
            f"FDA Adverse Event Data for {drug_name.title()}:\n"
            f"Most reported reactions: {', '.join(reactions)}"
        )

    except Exception as exc:
        logger.debug("OpenFDA fetch error: %s", exc)
        return ""


# ── Main entry point ───────────────────────────────────────────────────────────

async def get_live_context(query: str) -> str:
    """
    Fetch live medical context from PubMed, RxNorm, and OpenFDA concurrently.
    Hard timeout: LIVE_CONTEXT_TIMEOUT seconds.
    Returns a plain text string to append to RAG context_chunks, or "" if all fail.

    Args:
        query: The reformulated search query from reformulate_for_retrieval()
    """
    drug_names = extract_drug_names(query)
    first_drug = drug_names[0] if drug_names else ""

    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            results = await asyncio.gather(
                fetch_pubmed_abstracts(query, session),
                fetch_drug_interactions(drug_names, session),
                fetch_fda_adverse_events(first_drug, session),
                return_exceptions=True,
            )
    except asyncio.TimeoutError:
        logger.debug("Live context: global timeout hit")
        return ""
    except Exception as exc:
        logger.debug("Live context: unexpected error: %s", exc)
        return ""

    parts = []
    for result in results:
        if isinstance(result, str) and result.strip():
            parts.append(result.strip())
        # Exceptions from return_exceptions=True are silently skipped

    if not parts:
        return ""

    combined = "\n\n".join(parts)
    return combined[:MAX_CONTEXT_CHARS]
