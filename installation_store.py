import functools
from google.cloud import firestore
from typing import Optional
from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore
from slack_sdk.oauth.installation_store.models import Installation
import cachetools



class SlackMusicInstallationStore(AsyncInstallationStore):
    def __init__(self):
        # Initialize Firestore client
        self.db = firestore.AsyncClient()

        self.cache = cachetools.TTLCache(maxsize=128, ttl=300)

    async def async_save(self, installation: Installation):
        """
        Save the installation object in Firestore.
        If an installation with the same enterprise_id, team_id, and user_id exists, it will be updated.
        Also update the cache after saving to Firestore.
        """
        doc_id = f"{installation.enterprise_id}-{installation.team_id}-{installation.user_id}"
        installation_data = {
            "enterprise_id": installation.enterprise_id,
            "team_id": installation.team_id,
            "user_id": installation.user_id,
            "installation_data": installation.to_dict(),  # Assuming Installation has a to_dict() method
            "is_enterprise_install": installation.is_enterprise_install,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        
        # Save the installation data into Firestore
        await self.db.collection("installations").document(doc_id).set(installation_data)
        
        # Update cache with the latest installation (store as JSON)
        cache_key = self._build_cache_key(installation.enterprise_id, installation.team_id, installation.user_id)
        self._add_to_cache(cache_key, installation)

    async def async_find_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Installation]:
        """
        Find an installation by enterprise_id, team_id, and optionally user_id.
        If user_id is absent, this method returns the latest installation for the given enterprise/team.
        Use an in-memory LRU cache to store and retrieve installations in JSON format.
        """
        # Step 1: Try to get installation from cache (JSON)
        cache_key = self._build_cache_key(enterprise_id, team_id, user_id)
        cached_json = self._get_from_cache(cache_key)
        if cached_json:
            # Parse cached JSON back to Installation object
            return self.to_installation(cached_json)

        if user_id:
            # Case 1: Find installation with specific user_id
            doc_id = f"{enterprise_id}-{team_id}-{user_id}"
            doc_ref = self.db.collection("installations").document(doc_id)
            doc = await doc_ref.get()

            if doc.exists:
                data = doc.to_dict()
                installation_json = data["installation_data"]

                # Cache the JSON before returning
                self._add_to_cache(cache_key, installation_json)
                return self.to_installation(installation_json)
            else:
                raise ValueError(f"Installation {doc_id} not found")

        else:
            # Case 2: Find the latest installation in the workspace/org if user_id is not provided
            query = (
                self.db.collection("installations")
                .where(field_path="enterprise_id", op_string="==", value=enterprise_id)  # Filter by enterprise_id
                .where(field_path="team_id", op_string="==", value=team_id)  # Filter by team_id
                .order_by("created_at", direction=firestore.Query.DESCENDING)  # Order by latest
                .limit(1)  # Get the latest installation
            )
            docs = query.stream()  # This is an async generator, no await here

            # Process the result
            async for doc in docs:
                data = doc.to_dict()
                latest_installation_json = data["installation_data"]
                # Cache the JSON before returning
                self._add_to_cache(cache_key, latest_installation_json)
                return self.to_installation(latest_installation_json)

            raise ValueError("No installation found for the workspace")

    def to_installation(self, data: dict) -> Installation:
        return Installation(**data)

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
        return f"{enterprise_id}-{team_id}-{user_id if user_id else 'latest'}"