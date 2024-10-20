import functools
from google.cloud import firestore
from typing import Optional
from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore
from slack_sdk.oauth.installation_store.models import Installation
import cachetools
from models.users import User



class SlackMusicUserStore():

    def __init__(self):
        # Initialize Firestore client
        self.db = firestore.AsyncClient()

        self.cache = cachetools.TTLCache(maxsize=128, ttl=300)

    async def get_user(self, user_id: str) -> Optional[User]:
        """
        Get a user's data from Firestore using user_id.
        """
        doc = await self.db.collection("users").document(user_id).get()
        if doc.exists:
            return User(**doc.to_dict())
        return None

    async def save_user(self, user_id: str, user: User):
        """
        Save a user's data in Firestore using user_id.
        """
        user_data = user.model_dump(mode='json')
        await self.db.collection("users").document(user_id).set(user_data)

    ### Cache Layer ###

    def _get_from_cache(self, cache_key: str) -> Optional[dict]:
        """
        Retrieve an installation's JSON data from the in-memory cache using cachetools.TTLCache.
        """
        return self.cache.get(cache_key)

    def _add_to_cache(self, cache_key: str, installation_json: dict):
        """
        Add an installation's JSON data to the in-memory cache using cachetools.TTLCache.
        """
        self.cache[cache_key] = installation_json

    def _build_cache_key(self, enterprise_id: str, team_id: str, user_id: Optional[str]) -> str:
        """
        Build a cache key based on enterprise_id, team_id, and optionally user_id.
        """
        return "cache_key"  # f"{enterprise_id}-{team_id}-{user_id if user_id else 'latest'}"