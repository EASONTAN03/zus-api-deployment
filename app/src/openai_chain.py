import os
import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from .utils import load_config

logger = logging.getLogger(__name__)

config = load_config()
CHAT_MEMORY_WINDOW = config.get("chat_memory", {}).get("window_size", 5)

# Initialize OpenAI client
llm = ChatOpenAI(
    model=config.get("models", {}).get("llm_model", {}).get("name", "gpt-3.5-turbo"),
    temperature=config.get("models", {}).get("llm_model", {}).get("temperature", 0),
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

async def initialize_chains():
    """Initialize all LangChain components with direct prompt templates, including intent_chain."""
    try:
        # Product summary chain
        product_summary_prompt = PromptTemplate.from_template(
            """
You are a helpful assistant for ZUS Coffee. Based on the following product information, provide a concise and informative summary that answers the user's question.

Context:
{context}

User Question: {question}

Provide a clear, helpful response that directly addresses the user's question.
"""
        )
        
        product_summary_chain = product_summary_prompt | llm | StrOutputParser()
        
        # Outlet SQL query generation chain
        outlet_sql_prompt = PromptTemplate.from_template(
            """
You are a SQL expert. Generate a SQL query to find outlets based on the user's question.

Question: {question}

Given an input question, create a syntactically correct {dialect} SQL query 
to help find the answer. Unless the user specifies a specific number of results, 
always limit your query to at most {top_k} results using LIMIT.

IMPORTANT:
Do not add markdown blocks for the SQL Query.
- Return your answer ONLY as SQL Query, "SELECT ..."
- DO NOT include commentary or explanation.
- DO NOT include raw SQL outside of the JSON format.
- Always use pattern matching with LIKE and wrap values in %%
- Use only these tables and columns:

{table_info}

NOTES:
- The `opens_at` column contains weekly opening hours in a comma-separated text format, e.g.:
  "Monday, 8am–9:40pm, Tuesday, 8am–9:40pm, ..."
- For time-based queries (e.g., outlets open after 9pm), you only need to check for the time pattern (e.g., '%–9:%pm%' or '%–1%pm%') in the opens_at column, not per day. This is sufficient if all days have the same hours, which is common.
- For Selangor, use address LIKE '%Selangor%'.
- Use LOWER(column) for case-insensitive checks if needed.
- If the question asks for outlets open after a certain time, match any closing time later than that (e.g., 9:00pm, 9:10pm, 10pm, etc.).

EXAMPLES:
- For "Which outlets in Selangor open after 9pm?":
  SELECT * FROM outlets WHERE address LIKE '%Selangor%' AND (opens_at LIKE '%–9:%pm%' OR opens_at LIKE '%–1%pm%') LIMIT {top_k};
- Adjust the time pattern as needed for the user's question.

Be careful not to use columns that don't exist.
"""
        )

        
        outlet_write_query_chain = outlet_sql_prompt | llm | StrOutputParser()
        
        # Outlet summary chain
        outlet_summary_prompt = PromptTemplate.from_template(
            """
You are a helpful assistant for ZUS Coffee. Based on the SQL query results, provide a concise and informative summary that answers the user's question.

User Question: {question}
SQL Query: {query}
Query Results: {result}

Provide a clear, helpful response that directly addresses the user's question.
"""
        )
        
        outlet_summary_chain = outlet_summary_prompt | llm | StrOutputParser()

        # Intent classification chain
        intent_chain = create_intent_classification_chain()
        
        logger.info("All LangChain components initialized successfully")
        return product_summary_chain, outlet_write_query_chain, outlet_summary_chain, intent_chain
        
    except Exception as e:
        logger.error(f"Error initializing LangChain components: {e}")
        raise

def create_intent_classification_chain():
    """Create an intent classification chain"""
    prompt = PromptTemplate.from_template(
        """
Classify the user's intent into one of the following categories:
- product: Questions about ZUS Coffee products (drinkware, cups, tumblers, etc.)
- outlet: Questions about ZUS Coffee outlets (locations, stores, branches, etc.)
- general: General conversation or other topics

User input: {input}

Respond with only one word: "product", "outlet", or "general"
"""
    )
    
    return prompt | llm | StrOutputParser()
