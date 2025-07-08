import os
import json
import re
import logging
logger = logging.getLogger(__name__)

# Load configuration
def load_config():
    """Load configuration from config.json"""
    try:
        # Look for config.json in the parent directory (root of zus-api)
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}

config = load_config()

def extract_top_k_from_query(query: str) -> int:
    """Extract the number of results requested from the query"""
    patterns = [
        r'top\s+(\d+)',
        r'first\s+(\d+)',
        r'show\s+me\s+(\d+)',
        r'give\s+me\s+(\d+)',
        r'list\s+(\d+)',
        r'(\d+)\s+items?',
        r'(\d+)\s+products?',
        r'(\d+)\s+outlets?'
    ]
    for pattern in patterns:
        match = re.search(pattern, query.lower())
        if match:
            return int(match.group(1))
    return 3

def extract_final_answer(response: str) -> str:
    """Extract the final answer from the LLM response"""
    patterns = [
        r'Final Refined Answer:\s*(.+)',
        r'Answer:\s*(.+)',
        r'Summary:\s*(.+)',
        r'Based on the information:\s*(.+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return response.strip()

def detect_intent(query: str) -> str:
    """Detect the intent of the user query using config prompts"""
    try:
        from .openai_chain import create_intent_classification_chain
        chain = create_intent_classification_chain()
        result = chain.invoke({"input": query})
        return result.strip().lower()
    except Exception as e:
        logger.error(f"Error detecting intent: {e}")
        return "general"

def setup_logging():
    """Setup logging configuration from environment variables"""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_format = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_file = os.getenv("LOG_FILE", None)
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=handlers
    )
