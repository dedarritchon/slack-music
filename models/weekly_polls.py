from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Optional, Literal
from datetime import datetime

# enum with the possible statuses for a weekly poll
class PollStatus(str):
    submissions_open = 'submissions_open'
    voting_open = 'voting_open'
    closed = 'closed'

class SongSubmission(BaseModel):
    user_id: str
    song_link: HttpUrl
    submitted_at: datetime

class Vote(BaseModel):
    user_id: str
    song_voted_for: str
    voted_at: datetime

class PollResults(BaseModel):
    top_songs: List[str]  # List of song links or song IDs for the top 3 songs
    votes_count: Dict[str, int]  # {song_id: vote_count}
    created_at: datetime

class VoteInfo(BaseModel):
    voted_for: str
    voted_at: datetime
    voted_by: str

class SongInfo(BaseModel):
    id: str
    link: str
    title: str
    artist: str
    album: str
    image_url: Optional[str] = None
    submitted_by: str

class WeeklyPoll(BaseModel):
    poll_id: str  # Identifier for the week's poll
    category: str  # Music genre/category for the week
    created_at: datetime = datetime.now()
    status: Literal['submissions_open', 'voting_open', 'closed'] = PollStatus.submissions_open
    songs: Dict[str, SongInfo] = {} # Song ID to SongInfo mapping
    votes:  Dict[str, VoteInfo] = {} # User ID to VoteInfo mapping
    results: Optional[PollResults] = None  # Results after the poll is closed
    vote_counts: Dict[str, int] = {} # Example: {"song_id_1": 5, "song_id_2": 3}

    @classmethod
    def generate_poll_id(cls):
        # identifier of current week (2024-03-1 for example) where 1 is the umber of the week during the month
        return datetime.now().strftime('%Y-%m-%W')

    @classmethod
    def generate_new_weekly_poll(cls, poll_id: str, category: str = 'general') -> 'WeeklyPoll':
        return cls(
            poll_id=poll_id,
            category=category,
        )
