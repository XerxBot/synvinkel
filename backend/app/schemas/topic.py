from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TopicResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
