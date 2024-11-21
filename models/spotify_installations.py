from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Optional, Literal
from datetime import datetime


class SpotifyInstallation(BaseModel):
    user_id: str
    access_token: str
    refresh_token: str
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    expires_at: int
