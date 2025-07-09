from fastapi import APIRouter, HTTPException, Depends, Form, Header
from pydantic import BaseModel
from typing import List
import logging
from .vectorstore import search_products
from sqlalchemy import inspect
from .rate_limit import apply_rate_limit, get_user_identifier, load_users, save_users, pwd_context, create_access_token
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Pydantic models
class ChatInput(BaseModel):
    prompt: str

class ProductResponse(BaseModel):
    summary: str
    retrieved_products: List[dict] = []

class OutletResponse(BaseModel):
    summary: str
    sql_query: str = ""
    executed_sql_result: List[dict] = []

# Global variables (will be set by app.py)
embedding_model = None
product_summary_chain = None
outlet_write_query_chain = None
outlet_summary_chain = None
pinecone_index = None
outlets_sql_db = None

# JWT Auth Dependency
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")

# Add in-memory cache for chat responses
chat_cache = {}

def set_global_variables(emb_model, prod_chain, outlet_write_chain, outlet_sum_chain, pinecone_idx, sql_db, intent_chain_):
    """Set global variables from app.py"""
    global embedding_model, product_summary_chain, outlet_write_query_chain, outlet_summary_chain, pinecone_index, outlets_sql_db, intent_chain
    embedding_model = emb_model
    product_summary_chain = prod_chain
    outlet_write_query_chain = outlet_write_chain
    outlet_summary_chain = outlet_sum_chain
    pinecone_index = pinecone_idx
    outlets_sql_db = sql_db
    intent_chain = intent_chain_

@router.get("/products", response_model=ProductResponse)
async def get_products(query: str):
    """Get product information based on query"""
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty.")
    
    if not embedding_model or not product_summary_chain or not pinecone_index:
        raise HTTPException(status_code=503, detail="Models not loaded. Please try again later.")
    
    try:
        from .utils import extract_top_k_from_query, extract_final_answer
        
        actual_top_k = extract_top_k_from_query(query)
        logger.info(f"User query requested top_k: {actual_top_k}")
        
        # Use vectorstore's search_products
        products = search_products(query, top_k=actual_top_k)
        
        if not products:
            return ProductResponse(summary="No relevant products found.", retrieved_products=[])
        
        # Process results
        context_docs = []
        retrieved_products_info = []
        
        for product in products:
            context_docs.append(
                f"Product Name: {product['name']}\n"
                f"Category: {product['category_title']}\n"
                f"Colors Available: {product['color']}\n"
                f"Price: {product['price']}\n"
                f"Description Snippet: {product.get('description', '')}"
            )
            
            retrieved_products_info.append({
                "name": product['name'],
                "category": product['category_title'],
                "price": product['price'],
                "color": product['color'],
                "image": product['image'],
                "snippet": product.get('description', ''),
                "score": product['score']
            })
        
        if not context_docs:
            summary = "I couldn't find any relevant products based on your query. Please try a different query."
        else:
            context = "\n\n---\n\n".join(context_docs)
            full_llm_response = product_summary_chain.invoke({"context": context, "question": query})
            if isinstance(full_llm_response, dict):
                summary = extract_final_answer(full_llm_response.get('text', ''))
            else:
                summary = extract_final_answer(full_llm_response)
        
        return ProductResponse(summary=summary, retrieved_products=retrieved_products_info)
        
    except Exception as e:
        logger.error(f"Error during product retrieval: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during product retrieval: {e}")

@router.get("/outlets", response_model=OutletResponse)
async def get_outlets(query: str):
    """Get outlet information based on query"""
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty.")
    
    if not outlet_write_query_chain or not outlet_summary_chain:
        raise HTTPException(status_code=503, detail="Models not loaded. Please try again later.")
    
    try:
        from .utils import extract_top_k_from_query
        
        actual_top_k = extract_top_k_from_query(query)
        logger.info(f"User query requested top_k: {actual_top_k}")
        
        # Initialize state
        state = {"question": query}
        # Generate SQL query
        inspector = inspect(outlets_sql_db)
        columns = inspector.get_columns('outlets')
        # Format table_info as a string for the prompt
        table_info_str = 'outlets(' + ', '.join([col['name'] for col in columns]) + ')'
        response = outlet_write_query_chain.invoke({
            "question": state["question"],
            "top_k": actual_top_k,
            "dialect": outlets_sql_db.dialect,
            "table_info": table_info_str
        })
        if isinstance(response, dict):
            state["query"] = response.get('text', '')
        else:
            state["query"] = response

        print("SQL query being used:", state["query"])
        
        # Execute SQL query
        from .text2SQL import execute_sql_query
        state = execute_sql_query(state, outlets_sql_db)
        
        if len(state['result']) == 0:
            state["answer"] = "I couldn't find any relevant outlets based on your query. Please try a different query."
        else:
            response = outlet_summary_chain.invoke({"question": state["question"], "query": state["query"], "result": state["result"]})
            if isinstance(response, dict):
                state["answer"] = response.get('text', '')
            else:
                state["answer"] = response
        
        return OutletResponse(
            summary=state["answer"],
            sql_query=state["query"],
            executed_sql_result=state["result"]
        )
        
    except Exception as e:
        logger.error(f"Error during outlet query: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred while querying outlet data: {e}")

@router.post("/chat")
async def chat_endpoint(
    chat_input: ChatInput,
    user_id: str = Depends(get_user_identifier),
    _: bool = Depends(apply_rate_limit),
    authorization: str = Header(None)
):
    prompt = chat_input.prompt
    if prompt in chat_cache:
        return chat_cache[prompt]
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    try:
        from .utils import detect_intent
        intent = detect_intent(prompt)
        logger.info(f"Intent: {intent}")

        # Extract JWT token from Authorization header
        session_id = "global_unauthenticated_user"
        if authorization and authorization.startswith("Bearer "):
            session_id = authorization.split(" ", 1)[1]

        if isinstance(intent, dict):
            intent_type = intent.get("intent")
            missing_info = intent.get("missing_info", "")
            if missing_info:
                return {"message": f"I need more information: {missing_info}"}
            if intent_type == "product":
                response = await get_products(prompt)
                chat_cache[prompt] = response
                return response
            elif intent_type == "outlet":
                response = get_outlets(prompt)
                chat_cache[prompt] = response
                return response
            else:
                raise HTTPException(status_code=400, detail="Could not determine query type.")
        elif intent == "product":
            response = await get_products(prompt)
            chat_cache[prompt] = response
            return response
        elif intent == "outlet":
            response = get_outlets(prompt)
            chat_cache[prompt] = response
            return response
        else:
            raise HTTPException(status_code=400, detail="Could not classify intent.")
    except Exception as e:
        logger.error(f"Intent classification error: {e}")
        raise HTTPException(status_code=500, detail="Could not classify intent.")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "components": {
            "vectorstore": pinecone_index is not None,
            "embedding_model": embedding_model is not None,
            "product_chain": product_summary_chain is not None,
            "outlet_chains": outlet_write_query_chain is not None and outlet_summary_chain is not None,
            "intent_chain": intent_chain is not None if 'intent_chain' in globals() else False,
            "outlets_sql_db": outlets_sql_db is not None,
            # add more as needed
        }
    }

@router.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users:
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_pw = pwd_context.hash(password)
    users[username] = {"username": username, "hashed_password": hashed_pw}
    save_users(users)
    return JSONResponse(content={"msg": "Registration successful"})

@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    user = users.get(username)
    if not user or not pwd_context.verify(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(data={"sub": username})
    return JSONResponse(content={"access_token": token, "token_type": "bearer"})