"""
Law Filter Module - Validates if a query is law-related
CORE SECURITY MODULE: Prevents non-legal queries from reaching the LLM
"""

import re
from typing import Tuple

# ==================== LEGAL KEYWORDS DATABASE ====================
LEGAL_KEYWORDS = {
    # Laws and Acts
    "law", "legal", "act", "statute", "regulation", "ordinance", "code",
    "constitutional", "amendment", "bill", "clause", "section", "article",
    
    # Legal Procedures
    "court", "trial", "litigation", "lawsuit", "appeal", "judgment", "verdict",
    "petition", "writ", "injunction", "subpoena", "deposition", "hearing",
    "plea", "bail", "parole", "probation", "custody", "verdict", "settlement",
    
    # Legal Professionals
    "lawyer", "attorney", "barrister", "solicitor", "counsel", "advocate",
    "judge", "magistrate", "jury", "prosecutor", "defendant", "plaintiff",
    "notary", "legal expert", "law firm", "bar association",
    
    # Rights and Duties
    "right", "duty", "obligation", "liability", "responsibility", "contract",
    "agreement", "clause", "warranty", "guarantee", "indemnity", "tort",
    "negligence", "breach", "violation", "compliance", "consent", "waiver",
    
    # Criminal Law
    "crime", "criminal", "felony", "misdemeanor", "offense", "assault",
    "theft", "robbery", "murder", "fraud", "forgery", "embezzlement",
    "bribery", "extortion", "perjury", "contempt", "obstruction", "warrant",
    
    # Civil Law
    "civil", "divorce", "custody", "alimony", "property", "inheritance",
    "succession", "will", "testament", "probate", "estate", "lease", "tenant",
    "landlord", "mortgage", "lien", "copyright", "patent", "trademark",
    
    # Family Law
    "marriage", "husband", "wife", "spouse", "child", "parent", "guardian",
    "adoption", "guardianship", "domestic", "spousal", "child support",
    "maintenance", "visitation", "joint custody", "sole custody",
    
    # Corporate/Business Law
    "corporation", "company", "business", "partnership", "liability",
    "shareholder", "director", "compliance", "regulation", "tax",
    "employment", "labor", "wage", "discrimination", "harassment",
    
    # Procedural Terms
    "filing", "document", "evidence", "testimony", "witness", "cross-examination",
    "objection", "motion", "appeal", "jurisdiction", "venue", "statute of limitations",
    
    # Legal Concepts
    "rights", "due process", "legal aid", "justice", "innocent", "guilty",
    "conviction", "acquittal", "sentencing", "precedent", "jurisdiction",
    "sovereign immunity", "doctrine", "principle", "jurisprudence",
}

# ==================== NON-LEGAL KEYWORDS (Exclusion List) ====================
NON_LEGAL_KEYWORDS = {
    # Sports
    "sports", "football", "cricket", "basketball", "tennis", "match", "goal",
    "player", "team", "coach", "score", "winning", "championship", "playoff",
    
    # Entertainment
    "movie", "film", "actor", "actress", "comedy", "drama", "action",
    "bollywood", "hollywood", "celebrity", "music", "song", "album", "concert",
    "show", "netflix", "theatre", "play",
    
    # General Knowledge
    "science", "history", "geography", "mathematics", "biology", "physics",
    "chemistry", "astronomy", "space", "planet", "star", "weather", "climate",
    
    # Personal Advice
    "relationship", "dating", "love", "breakup", "depression", "anxiety",
    "mental health", "health", "medicine", "doctor", "hospital", "disease",
    "cooking", "recipe", "diet", "fitness", "workout", "exercise",
    
    # Technology (General)
    "programming", "code", "software", "hardware", "computer", "phone",
    "app", "web", "internet", "gaming", "video game", "console",
    
    # Others
    "weather", "politics", "news", "election", "politician", "minister",
}

# ==================== LEGAL DOMAIN PATTERNS ====================
LEGAL_PATTERNS = [
    r"\b(section|article|clause|paragraph|subsection|schedule)\s+\d+",  # Legal references
    r"\b(case|case law|precedent|ruling)\b",
    r"\b(constitution|constitutional)\b",
    r"\b(act|statute|ordinance|regulation)\s+of\s+\d{4}",  # Laws with years
    r"\b(indian penal code|ipc|indian constitution|constitution of india)\b",
    r"\b(supreme court|high court|district court)\b",
]

# ==================== LAW FILTER FUNCTION ====================
def is_legal_query(query: str) -> Tuple[bool, str]:
    """
    Validates if a query is law-related.
    
    Args:
        query (str): User's input question
        
    Returns:
        Tuple[bool, str]: (is_legal, reason)
        - is_legal: True if query is legal-related
        - reason: Explanation for the decision
    """
    
    query_lower = query.lower().strip()
    
    # ==================== STEP 1: Check for legal patterns ====================
    for pattern in LEGAL_PATTERNS:
        if re.search(pattern, query_lower):
            return True, "Legal reference detected (pattern match)"
    
    # ==================== STEP 2: Count legal keywords ====================
    legal_count = sum(1 for keyword in LEGAL_KEYWORDS if f"\\b{keyword}\\b" in query_lower or keyword in query_lower)
    non_legal_count = sum(1 for keyword in NON_LEGAL_KEYWORDS if keyword in query_lower)
    
    # ==================== STEP 3: Decision Logic ====================
    
    # If non-legal keywords present and no legal keywords, reject
    if non_legal_count > 0 and legal_count == 0:
        return False, "Non-legal topic detected"
    
    # If legal keywords found, accept (even if short)
    if legal_count > 0:
        return True, f"Legal keywords detected ({legal_count} matches)"
    
    # ==================== STEP 4: Query Length Check ====================
    # Short, vague queries without keywords are likely non-legal
    # But only reject if they don't contain common legal question patterns
    if len(query_lower.split()) < 3:
        # Check for legal question patterns even in short queries
        if not any(keyword in query_lower for keyword in ["court", "law", "legal", "ipc", "case", "act", "right"]):
            return False, "Query too vague and lacks legal context"
    
    # ==================== STEP 5: Intent Analysis (Simple Heuristic) ====================
    question_words = ["what", "how", "why", "when", "where", "who", "can", "should", "is", "are"]
    starts_with_question = any(query_lower.startswith(word) for word in question_words)
    
    # If it's a question but contains NO legal keywords, likely non-legal
    if starts_with_question and legal_count == 0:
        return False, "Question lacks legal context"
    
    # Default: Accept if not clearly non-legal
    return True, "Query appears to be law-related"


# ==================== TESTING FUNCTION ====================
def test_law_filter():
    """Test the law filter with various queries"""
    test_cases = [
        # Legal queries (should pass)
        ("What are my rights under Indian Constitution?", True),
        ("How do I file a case in Supreme Court?", True),
        ("What is IPC Section 420?", True),
        ("Can I divorce my spouse under Hindu Marriage Act?", True),
        ("What is contractual breach?", True),
        
        # Non-legal queries (should fail)
        ("Who won the cricket match yesterday?", False),
        ("What is the best recipe for biryani?", False),
        ("Tell me about Bollywood movies", False),
        ("How to build a website?", False),
        ("What's the weather today?", False),
    ]
    
    print("\n" + "="*60)
    print("LAW FILTER TEST RESULTS")
    print("="*60)
    
    for query, expected in test_cases:
        is_legal, reason = is_legal_query(query)
        status = "✓ PASS" if is_legal == expected else "✗ FAIL"
        print(f"\n{status}")
        print(f"Query: {query}")
        print(f"Expected: {'Legal' if expected else 'Non-Legal'}")
        print(f"Got: {'Legal' if is_legal else 'Non-Legal'}")
        print(f"Reason: {reason}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    test_law_filter()
