from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector
import uuid

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, index=True)
    tenant_id = Column(String, index=True)
    status = Column(String, default="Uploaded")
    s3_key = Column(String)
    
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"))
    content = Column(Text)
    content_hash = Column(String, unique=True, index=True)
    embedding = Column(Vector(768)) # Adjust dimensions based on chosen embedding model (e.g. 768 for average BERT-based model)
    metadata_json = Column(JSON)
    
    document = relationship("Document", back_populates="chunks")
