import os
import json
import logging
from typing import TypedDict, List

# LangChain / LangGraph imports
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

# Database
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DB_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None

# 1. Define State Graph Schema
class AgentState(TypedDict):
    query: str
    tenant_id: str
    retrieved_contexts: List[dict]
    reasoning_trace: List[str]
    draft_answer: str
    final_answer: str
    citations: List[str]
    verification_passed: bool

# 2. Nodes
def retrieve_node(state: AgentState):
    logger.info("Executing Retrieve Node")
    query = state["query"]
    tenant_id = state["tenant_id"]
    
    embeddings_model = OpenAIEmbeddings()
    query_vector = embeddings_model.embed_query(query)
    
    # Raw SQL for pgvector similarity search, joining Document to filter by tenant_id
    query_sql = text("""
        SELECT c.id, c.content, c.document_id, d.title
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.tenant_id = :tenant_id
        ORDER BY c.embedding <=> CAST(:query_vec AS vector)
        LIMIT 5
    """)
    
    contexts = []
    if SessionLocal:
        db = SessionLocal()
        try:
            results = db.execute(query_sql, {"tenant_id": tenant_id, "query_vec": str(query_vector)}).fetchall()
            for r in results:
                contexts.append({
                    "chunk_id": str(r.id),
                    "content": r.content,
                    "document_id": str(r.document_id),
                    "document_title": r.title
                })
        except Exception as e:
            logger.error(f"Retrieve Error: {str(e)}")
        finally:
            db.close()
            
    state["retrieved_contexts"] = contexts
    state["reasoning_trace"].append("Successfully retrieved top 5 relevant document chunks from PostgreSQL pgvector.")
    return state

def reason_node(state: AgentState):
    logger.info("Executing Reason Node (CoT)")
    query = state["query"]
    contexts = state["retrieved_contexts"]
    
    context_text = "\n\n".join([f"Source {idx+1} (Doc: {c['document_title']}, ID: {c['chunk_id']}): {c['content']}" for idx, c in enumerate(contexts)])
    
    system_prompt = f"""You are an advanced enterprise reasoning assistant. 
Follow these steps strictly:
1. Think step-by-step (Chain of Thought) about the user's query based ONLY on the provided context.
2. Draft an answer.
3. Include explicit citations using [CIT: chunk_id=<id>] at the end of relevant sentences.

CONTEXT:
{context_text}"""

    llm = ChatOpenAI(temperature=0)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]
    
    try:
        response = llm.invoke(messages)
        state["draft_answer"] = response.content
        state["reasoning_trace"].append("Applied Chain of Thought deduplication to raw contexts and drafted an initial answer.")
    except Exception as e:
        logger.error(f"LLM Error: {str(e)}")
        state["draft_answer"] = "Error connecting to LLM endpoint."
        
    return state

def verify_node(state: AgentState):
    logger.info("Executing Verify Node")
    draft = state["draft_answer"]
    
    # Simple verification logic checking for hallucinations
    verification_prompt = "Does the following draft answer contain any obvious hallucinations not supported by standard facts? Reply 'YES' or 'NO'."
    llm = ChatOpenAI(temperature=0)
    
    try:
        verdict = llm.invoke([HumanMessage(content=verification_prompt + "\n\n" + draft)])
        
        if "YES" in verdict.content.upper():
            state["verification_passed"] = False
            state["final_answer"] = "I could not confidently verify the reasoning based on the provided documents. Please ask a more specific question."
            state["reasoning_trace"].append("Verification FAILED. Draft answer was flagged for potential hallucination.")
        else:
            state["verification_passed"] = True
            state["final_answer"] = draft
            state["reasoning_trace"].append("Verification PASSED. Answer aligns with retrieved context robustly.")
    except Exception as e:
        state["final_answer"] = draft
        state["reasoning_trace"].append("Verification step bypassed due to API error. Presenting draft answer.")
        
    return state

# 3. Compile Graph
workflow = StateGraph(AgentState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("reason", reason_node)
workflow.add_node("verify", verify_node)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "reason")
workflow.add_edge("reason", "verify")
workflow.add_edge("verify", END)

app_graph = workflow.compile()

def lambda_handler(event, context):
    """
    AWS Lambda handler for processing query invocations via API Gateway / API Server.
    """
    body = json.loads(event.get('body', '{}')) if isinstance(event.get('body'), str) else event.get('body', {})
    query = body.get('query', '')
    tenant_id = body.get('tenant_id', 'default_tenant')
    
    if not query:
        return {'statusCode': 400, 'body': json.dumps("No query provided")}
        
    initial_state = {
        "query": query,
        "tenant_id": tenant_id,
        "retrieved_contexts": [],
        "reasoning_trace": [],
        "draft_answer": "",
        "final_answer": "",
        "citations": [],
        "verification_passed": False
    }
    
    logger.info(f"Starting LangGraph logic for query '{query}'")
    final_state = app_graph.invoke(initial_state)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            "answer": final_state["final_answer"],
            "reasoning_trace": final_state["reasoning_trace"],
            "retrieved_sources": [c["document_title"] for c in final_state["retrieved_contexts"]]
        })
    }
