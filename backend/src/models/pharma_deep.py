"""Private, durable research jobs. Public evidence is never shared across account reports."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from src.db.base import Base


class PharmaDeepResearch(Base):
    __tablename__='pharma_deep_research'
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    owner_id=Column(UUID(as_uuid=True),ForeignKey('users.id',ondelete='CASCADE'),nullable=False)
    query=Column(Text,nullable=False)
    status=Column(String(24),nullable=False,default='draft')
    stage=Column(String(24),nullable=False,default='plan')
    plan=Column(JSONB,nullable=False,default=dict)
    checkpoint=Column(JSONB,nullable=False,default=dict)
    activity=Column(JSONB,nullable=False,default=list)
    report=Column(JSONB,nullable=True)
    revision=Column(Integer,nullable=False,default=1)
    lease_owner=Column(String(36),nullable=True)
    lease_until=Column(DateTime(timezone=True),nullable=True)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    started_at=Column(DateTime(timezone=True),nullable=True)
    queued_at=Column(DateTime(timezone=True),nullable=True)
    completed_at=Column(DateTime(timezone=True),nullable=True)
    updated_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
    __table_args__=(Index('ix_pharma_deep_owner_created','owner_id','created_at'),Index('ix_pharma_deep_queue','status','lease_until','created_at'))
