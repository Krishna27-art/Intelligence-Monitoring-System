import os
import re

_AI_CLASSIFIER = None
_AI_LOAD_ATTEMPTED = False

# HIGH VALUE KEYWORDS: Only run AI if these are present (Saves 90% CPU)
FINANCIAL_KEYWORDS = re.compile(
    r'(profit|loss|revenue|dividend|deal|contract|acquisition|merged|takeover|order|awarded|board meeting|results|guidance)', 
    re.IGNORECASE
)

def get_ai_classifier():
    """Load the transformer model only when explicitly enabled."""
    global _AI_CLASSIFIER, _AI_LOAD_ATTEMPTED
    if _AI_CLASSIFIER is not None:
        return _AI_CLASSIFIER
    if _AI_LOAD_ATTEMPTED:
        return None

    enabled = os.getenv("USE_TRANSFORMERS_SENTIMENT", "").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        _AI_LOAD_ATTEMPTED = True
        return None

    _AI_LOAD_ATTEMPTED = True
    try:
        from transformers import pipeline
        print("Loading AI Model (This might take a minute on first run)...")
        _AI_CLASSIFIER = pipeline("sentiment-analysis", model="finiteautomata/bertweet-base-sentiment-analysis")
        print("AI Model Loaded Successfully!")
        return _AI_CLASSIFIER
    except Exception as e:
        print(f"AI Load failed ({e}). Using ultra-fast Rule-Based Fallback.")
        return None

def analyze_headline(headline: str) -> tuple:
    """Returns: (Sentiment Label, Score from -100 to +100, 2-line Summary)"""
    
    # SMART FILTER: If it's not financial news, use the ultra-fast rule-based fallback immediately
    if not FINANCIAL_KEYWORDS.search(headline):
        return rule_based_fallback(headline)

    ai_classifier = get_ai_classifier()
    if ai_classifier:
        try:
            result = ai_classifier(headline[:128])[0] # Limit tokens for speed and model compatibility
            label = result['label'].upper() # POS, NEG, NEU
            prob = result['score']
            
            # Convert to -100 to +100 scale
            if label == 'POS':
                sentiment = "POSITIVE"
                score = int(prob * 100)
            elif label == 'NEG':
                sentiment = "NEGATIVE"
                score = int(-prob * 100)
            else:
                sentiment = "NEUTRAL"
                score = 0
            
            summary = headline[:100] + "..." if len(headline) > 100 else headline
            return sentiment, score, summary
        except:
            pass # Fall through to rule-based if GPU/OOM error happens

    # --- ULTRA FAST RULE-BASED FALLBACK ---
    return rule_based_fallback(headline)

def rule_based_fallback(headline: str) -> tuple:
    """Ultra-fast sentiment detection using keyword counting"""
    headline_lower = headline.lower()
    pos_words = ['surge', 'profit', 'rise', 'gain', 'upgrade', 'win', 'wins', 'growth', 'launch', 'beat', 'strong']
    neg_words = ['fall', 'loss', 'crash', 'downgrade', 'fraud', 'ban', 'decline', 'debt', 'fine', 'penalty', 'regulatory', 'probe', 'default', 'pressure']
    
    score = 0
    for word in pos_words: score += 20 if word in headline_lower else 0
    for word in neg_words: score -= 20 if word in headline_lower else 0
    
    if score > 0: return "POSITIVE", min(score, 100), headline[:100]
    elif score < 0: return "NEGATIVE", max(score, -100), headline[:100]
    else: return "NEUTRAL", 0, headline[:100]

def extract_metadata(headline: str) -> tuple:
    """Extracts Update Type and Key Metric from headline"""
    headline_lower = headline.lower()
    
    # Update Types
    if any(x in headline_lower for x in ['profit', 'quarterly', 'result', 'revenue']):
        update_type = 'PROFIT'
    elif any(x in headline_lower for x in ['deal', 'order', 'contract', 'win', 'signed']):
        update_type = 'DEAL'
    elif any(x in headline_lower for x in ['dividend', 'payout']):
        update_type = 'DIVIDEND'
    elif any(x in headline_lower for x in ['appointment', 'md', 'ceo', 'cfo', 'resigns']):
        update_type = 'MANAGEMENT'
    else:
        update_type = 'NEWS'
        
    # Key Metrics (Greedy extraction)
    metric = ""
    # Look for percentages
    pct_match = re.search(r'(\d+%|\d+\s?percent)', headline)
    if pct_match:
        metric = f"Up {pct_match.group(1)}" if 'up' in headline_lower or 'rise' in headline_lower else f"Down {pct_match.group(1)}"
    
    # Look for Cr (Crores)
    cr_match = re.search(r'(Rs|INR)?\s?(\d+,?\d+)\s?(Cr|Crore)', headline, re.IGNORECASE)
    if cr_match:
        metric = f"Rs {cr_match.group(2)} Cr"
        
    return update_type, metric
