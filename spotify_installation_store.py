from google.cloud import firestore
import cachetools
from typing import Optional
from datetime import datetime
from models.spotify_installations import SpotifyInstallation  # Import the model


class SlackSpotifyInstallationStore():

    def __init__(self):
        # Initialize Firestore client
        self.db = firestore.AsyncClient()

        # In-memory cache with TTL
        self.cache = cachetools.TTLCache(maxsize=128, ttl=300)

    async def get_installation(self, team_id: str) -> Optional[SpotifyInstallation]:
        """
        Retrieve the Spotify installation details for a given team_id.
        Checks the cache first, then Firestore.
        """
        cache_key = self._build_cache_key(team_id)
        cached_installation = self._get_from_cache(cache_key)
        if cached_installation:
            return SpotifyInstallation(**cached_installation)

        # Access the document correctly (via .document())
        doc_ref = self.db.collection(f"workspaces").document(team_id).collection('spotify_installations').document('spotify_installation')
        doc = await doc_ref.get()
        if doc.exists:
            self._add_to_cache(cache_key, doc.to_dict())
            return SpotifyInstallation(**doc.to_dict())
        return None

    async def save_installation(self, team_id: str, installer_user_id: str, access_token: str, refresh_token: str, expires_at: int):
        """
        Save a new Spotify installation for a given team.
        """
        installation_data = {
            "user_id": installer_user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "expires_at": expires_at
        }

        # Save the installation data to the correct document
        doc_ref = self.db.collection(f"workspaces").document(team_id).collection('spotify_installations').document('spotify_installation')
        await doc_ref.set(installation_data)

        # Cache the data for quicker access
        cache_key = self._build_cache_key(team_id)
        self._add_to_cache(cache_key, installation_data)

    async def update_tokens(self, team_id: str, access_token: str, refresh_token: str, expires_at: int):
        """
        Update the access token, refresh token, and expiration time for an existing installation.
        """
        installation_ref = self.db.collection(f"workspaces").document(team_id).collection('spotify_installations').document('spotify_installation')

        # Update tokens and expiration time in Firestore
        await installation_ref.update({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "updated_at": datetime.now()  # Update the timestamp
        })

        # Also update the cache
        cache_key = self._build_cache_key(team_id)
        self._add_to_cache(cache_key, {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "updated_at": datetime.now()  # Update the timestamp
        })

    ### Cache Layer ###

    def _get_from_cache(self, cache_key: str) -> Optional[dict]:
        """
        Retrieve Spotify installation data from the in-memory cache.
        """
        return self.cache.get(cache_key)

    def _add_to_cache(self, cache_key: str, installation_data: dict):
        """
        Add Spotify installation data to the in-memory cache.
        """
        self.cache[cache_key] = installation_data

    def _build_cache_key(self, team_id: str) -> str:
        """
        Build a unique cache key based on team_id.
        """
        return f"spotify-installation-{team_id}"
