import functools
from google.cloud import firestore
from typing import Optional
from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore
from slack_sdk.oauth.installation_store.models import Installation
import cachetools
from models.weekly_polls import WeeklyPoll, SongInfo



class SlackMusicWeeklyPollsStore():

    def __init__(self):
        # Initialize Firestore client
        self.db = firestore.AsyncClient()

        self.cache = cachetools.TTLCache(maxsize=128, ttl=300)

    async def get_poll(self, team_id:str, poll_id: str) -> Optional[WeeklyPoll]:
        # /workspaces/{team_id}/weekly_polls/{poll_id}

        cache_key = self._build_cache_key(team_id, poll_id)
        cached_poll = self._get_from_cache(cache_key)
        if cached_poll:
            return WeeklyPoll(**cached_poll)

        doc = await self.db.collection(f"workspaces/{team_id}/weekly_polls").document(poll_id).get()
        if doc.exists:
            self._add_to_cache(cache_key, doc.to_dict())
            return WeeklyPoll(**doc.to_dict())
        return None

    async def save_poll(self, team_id: str, poll: WeeklyPoll):
        # /workspaces/{team_id}/weekly_polls/{poll_id}
        poll_data = poll.model_dump(mode='json')
        await self.db.collection(f"workspaces/{team_id}/weekly_polls").document(poll.poll_id).set(poll_data)
        cache_key = self._build_cache_key(team_id, poll.poll_id)
        self._add_to_cache(cache_key, poll_data)

    async def cast_vote(self, team_id: str, poll_id: str, song_id: str, user_id: str):
        # Reference to the weekly poll
        poll_ref = self.db.collection(f"workspaces/{team_id}/weekly_polls").document(poll_id)

        # Firestore transaction to ensure atomic vote count increment
        @firestore.transactional
        def increment_vote(transaction, poll_ref):
            # Read poll document in the transaction
            poll_snapshot = poll_ref.get(transaction=transaction)

            # Update vote counts
            vote_counts = poll_snapshot.get('vote_counts', {})
            if song_id in vote_counts:
                vote_counts[song_id] += 1
            else:
                vote_counts[song_id] = 1

            # Write the updated vote counts back
            transaction.update(poll_ref, {'vote_counts': vote_counts})

        # Start the transaction
        transaction = self.db.transaction()
        await increment_vote(transaction, poll_ref)

        # Optionally, record the user's vote
        vote_ref = poll_ref.collection('votes').document(user_id)
        vote_ref.set({'song_voted_for': song_id, 'voted_at': firestore.SERVER_TIMESTAMP})

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

    def _build_cache_key(self, team_id: str, poll_id: str) -> str:
        """
        Build a cache key based on enterprise_id, team_id, and optionally user_id.
        """
        return f"{team_id}-{poll_id}"