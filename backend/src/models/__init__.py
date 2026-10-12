"""Import all models here so Alembic autogenerate can detect them."""
from src.models.user import User
from src.models.space import Space, SpaceMember, SpaceInvite, SpaceFile, SpaceFileChunk, SpaceThread
from src.models.thread import Thread
from src.models.message import Message
from src.models.source import Source
from src.models.collection import Collection, collection_threads
__all__ = [
    "User",
    "Space", "SpaceMember", "SpaceInvite", "SpaceFile", "SpaceFileChunk", "SpaceThread",
    "Thread",
    "Message",
    "Source",
    "Collection", "collection_threads",
]
