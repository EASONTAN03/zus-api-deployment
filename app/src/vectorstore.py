import os
import logging
import numpy as np
from typing import List, Dict, Any
from .utils import load_config
import openai
from pinecone import Pinecone, ServerlessSpec

logger = logging.getLogger(__name__)

config = load_config()

# Global variables
pinecone_index = None
product_data = []

async def initialize_vectorstore():
    """Initialize the vector store for semantic search using Pinecone"""
    global pinecone_index, product_data
    
    try:
        # Load configuration
        pinecone_config = config.get("pinecone", {})
        
        # Initialize Pinecone
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        index_name = pinecone_config.get("index_name", "zus-products")
        
        if not pinecone_api_key:
            raise ValueError("Pinecone API key not found. Please set the PINECONE_API_KEY environment variable.")
        
        # Initialize Pinecone client
        pc = Pinecone(api_key=pinecone_api_key)
        
        # Get or create index
        if index_name not in pc.list_indexes().names():
            logger.info(f"Creating Pinecone index: {index_name}")
            dimension = 1536  # OpenAI text-embedding-3-small outputs 1536-dim vectors
            metric = pinecone_config.get("metric", "cosine")
            cloud = pinecone_config.get("cloud", "aws")
            region = pinecone_config.get("region", "us-east-1")
            
            pc.create_index(
                name=index_name,
                dimension=dimension,
                metric=metric,
                spec=ServerlessSpec(
                    cloud=cloud,
                    region=region
                )
            )
        
        # Connect to index
        pinecone_index = pc.Index(index_name)
        logger.info(f"Connected to Pinecone index: {index_name}")
        
        # Load product data
        logger.info("Loading product data...")
        product_data = load_product_data()
        
        if not product_data:
            logger.warning("No product data found")
            return pinecone_index
        
        # Check if index is empty and needs to be populated
        index_stats = pinecone_index.describe_index_stats()
        if index_stats.get("total_vector_count", 0) == 0:
            logger.info("Index is empty, populating with product data...")
            await populate_pinecone_index()
        
        logger.info(f"Vector store initialized with {len(product_data)} products")
        return pinecone_index
        
    except Exception as e:
        logger.error(f"Error initializing vector store: {e}")
        raise

async def populate_pinecone_index():
    """Populate Pinecone index with product data"""
    global pinecone_index, product_data
    
    try:
        # Prepare data for Pinecone
        vectors = []
        
        for i, product in enumerate(product_data):
            # Create text representation of product
            text = f"{product.get('name', '')} {product.get('category_title', '')} {product.get('description', '')}"
            
            # Generate embedding
            embedding = get_openai_embedding(text)
            
            # Prepare metadata
            metadata = {
                "text": str(text),
                "name": str(safe_value(product.get('name', ''), "")),
                "category_title": str(safe_value(product.get('category_title', ''), "")),
                "image": str(safe_value(product.get('image', ''), "")),
                "price": float(safe_value(product.get('price', 0), 0)),
                "color": str(safe_value(product.get('color', ''), "")),
                "description": str(safe_value(product.get('description', ''), ""))
            }
            
            vectors.append({
                "id": f"product_{i}",
                "values": embedding,
                "metadata": metadata
            })
        
        # Upsert to Pinecone in batches
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            pinecone_index.upsert(vectors=batch)
            logger.info(f"Upserted batch {i//batch_size + 1}/{(len(vectors) + batch_size - 1)//batch_size}")
        
        logger.info(f"Successfully populated Pinecone index with {len(vectors)} products")
        
    except Exception as e:
        logger.error(f"Error populating Pinecone index: {e}")
        raise

def safe_value(val, default=""):
    if val is None:
        return default
    if isinstance(val, float) and (np.isnan(val) or str(val).lower() == "nan"):
        return default
    if isinstance(val, str) and val.lower() == "nan":
        return default
    return val

def load_product_data() -> List[Dict[str, Any]]:
    """Load product data from CSV file"""
    try:
        import pandas as pd
        
        filepaths = config.get("filepaths", {})
        products_config = filepaths.get("products", {})
        
        # Try multiple possible paths
        possible_paths = [
            products_config.get("csv", "data/zus_products.csv")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Loading product data from {path}")
                df = pd.read_csv(path)
                return df.to_dict('records')
        
        logger.warning("No product data file found")
        return []
        
    except Exception as e:
        logger.error(f"Error loading product data: {e}")
        return []

def search_products(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """Search for products using semantic similarity with Pinecone"""
    global pinecone_index
    
    if not pinecone_index:
        logger.error("Vector store not initialized")
        return []
    
    try:
        # Get top_k from config if not provided
        if top_k is None:
            top_k = config.get("pinecone", {}).get("top_k", 3)
        
        # Generate query embedding
        query_embedding = get_openai_embedding(query)
        
        # Query Pinecone
        results = pinecone_index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True
        )
        
        # Process results
        products = []
        for match in results.matches:
            if match.metadata:
                product = {
                    "name": match.metadata.get("name", ""),
                    "category_title": match.metadata.get("category_title", ""),
                    "image": match.metadata.get("image", ""),
                    "price": match.metadata.get("price", ""),
                    "color": match.metadata.get("color", ""),
                    "description": match.metadata.get("description", ""),
                    "score": match.score
                }
                products.append(product)
        
        return products
        
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        return []

def get_openai_embedding(text: str, model: str = "text-embedding-3-small") -> list:
    """Get embedding from OpenAI for a given text and model."""
    response = openai.embeddings.create(
        input=[text],
        model=model
    )
    return response.data[0].embedding
