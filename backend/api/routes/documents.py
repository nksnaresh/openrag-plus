import uuid
import os
import boto3
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_db, get_current_user
from db.models import Document
from core.config import settings

router = APIRouter()

@router.post("/upload-url")
def get_presigned_url(filename: str, db: Session = Depends(get_db)):
    """
    Generate a pre-signed URL to upload a document directly to S3.
    """
    doc_id = uuid.uuid4()
    # Hardcoded default tenant for MVP testing. In production, grab from current_user JWT.
    tenant_id = "default_tenant"
    s3_key = f"raw/{tenant_id}/{doc_id}/{filename}"
    
    bucket_name = os.environ.get("AWS_S3_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="AWS_S3_BUCKET environment variable is not set. Please check your backend/.env file.")
        
    try:
        s3_client = boto3.client('s3', region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        url = s3_client.generate_presigned_url(
            'put_object', 
            Params={'Bucket': bucket_name, 'Key': s3_key, 'ContentType': 'application/pdf'}, 
            ExpiresIn=3600
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Create DB entry for tracking the ingestion lifecycle
    new_doc = Document(
        id=doc_id,
        title=filename,
        tenant_id=tenant_id,
        status="Pending Upload",
        s3_key=s3_key
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    
    return {"upload_url": url, "document_id": str(doc_id)}

@router.post("/{doc_id}/query")
def query_document(doc_id: str, query: str, db: Session = Depends(get_db)):
    """
    Query a document using the LangGraph reasoning engine via AWS Lambda.
    """
    # MOCK: In production, trigger AWS Lambda or hit an API Gateway endpoint backed by Lambda
    # which executes the LangGraph flow: Retrieve -> Reasoning -> Verification -> Answer
    
    return {
        "answer": f"Mock reasoning trace and answer for query: '{query}' on doc: {doc_id}",
        "citations": [{"node": "chunk-123", "page": 1}],
        "intermediate_steps": ["Retrieved data segments from pgvector", "Applied Chain of Thought reasoning", "Verified conclusions against rules"]
    }
