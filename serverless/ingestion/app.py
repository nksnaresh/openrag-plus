import os
import json
import urllib.parse
import hashlib
import logging
import uuid
import boto3

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pgvector.sqlalchemy import Vector

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DB_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
SessionLocal = sessionmaker(bind=engine) if engine else None

# Inline DB models for the Lambda function to avoid complex layer packaging for MVP
from sqlalchemy import Column, String, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()
class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True)
    status = Column(String)

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    content = Column(Text)
    content_hash = Column(String, unique=True, index=True)
    # 1536 is standard for OpenAI endpoints. Adjust if using BGE or E5 local models.
    embedding = Column(Vector(1536)) 
    metadata_json = Column(JSON)

def download_s3_file(bucket: str, key: str, local_path: str):
    s3_client = boto3.client('s3')
    s3_client.download_file(bucket, key, local_path)

def process_document(bucket: str, key: str):
    logger.info(f"Processing document from s3://{bucket}/{key}")
    
    # Parse object key to find logical doc mappings: raw/{tenant_id}/{doc_id}/{filename}
    parts = key.split('/')
    if len(parts) < 4:
        logger.error(f"Invalid key structure: {key}")
        return
    tenant_id, doc_id_str, filename = parts[1], parts[2], parts[3]
    doc_id = uuid.UUID(doc_id_str)
    
    local_file_path = f"/tmp/{filename}"
    download_s3_file(bucket, key, local_file_path)
    
    # 1. Parsing & Chunking Phase
    # Real implementation would have mimetypes mapping to various LangChain document loaders
    loader = PyPDFLoader(local_file_path) if filename.lower().endswith('.pdf') else None
    if not loader:
        logger.warning(f"Only PDF parsing is implemented for MVP. Skipping {filename}.")
        return
        
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(documents)
    
    # 2. Embedding Generation Phase
    embeddings_model = OpenAIEmbeddings() 
    texts = [chunk.page_content for chunk in chunks]
    embeddings = embeddings_model.embed_documents(texts)
    
    if not SessionLocal:
        logger.warning("No Postgres connection available. Skipping DB persistence.")
        return

    # 3. Transactional DB Persistence with Content-Hash Deduplication
    db = SessionLocal()
    try:
        # Optimistic status update
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "Indexing"
            db.commit()
            
        for chunk, embedding in zip(chunks, embeddings):
            content_hash = hashlib.sha256(chunk.page_content.encode('utf-8')).hexdigest()
            
            # Simple embedding cache / deduplication mechanism based on content string
            existing = db.query(DocumentChunk).filter(DocumentChunk.content_hash == content_hash).first()
            if not existing:
                new_chunk = DocumentChunk(
                    document_id=doc_id,
                    content=chunk.page_content,
                    content_hash=content_hash,
                    embedding=embedding,
                    metadata_json=chunk.metadata
                )
                db.add(new_chunk)
                
        if doc:
            doc.status = "Indexed"
            
        db.commit()
        logger.info(f"Successfully processed and indexed {len(chunks)} chunks for {doc_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database insertion failed: {str(e)}")
        if doc:
            doc.status = "Failed"
            db.commit()
    finally:
        db.close()
        if os.path.exists(local_file_path):
            os.remove(local_file_path)

def lambda_handler(event, context):
    """
    Serverless handler parsing batches of SQS messages containing S3 bucket events.
    Failure within the loop surfaces the exception so the message routes to DLQ automatically.
    """
    for record in event.get('Records', []):
        try:
            body = json.loads(record['body'])
            # S3 event payload wrapped inside SQS
            if 'Records' in body:
                for s3_event in body['Records']:
                    bucket = s3_event['s3']['bucket']['name']
                    key = urllib.parse.unquote_plus(s3_event['s3']['object']['key'])
                    process_document(bucket, key)
            else:
                logger.warning("Unrecognized message format received from SQS.")
        except Exception as e:
            logger.error(f"Error processing record - returning to DLQ: {str(e)}")
            raise e
            
    return {
        'statusCode': 200,
        'body': json.dumps('Serverless pipeline iteration completed.')
    }
