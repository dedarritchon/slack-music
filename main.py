import os
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_bolt.oauth.async_oauth_flow import AsyncOAuthFlow
from slack_bolt.oauth.async_callback_options import DefaultAsyncCallbackOptions
from slack_sdk.oauth.installation_store.models import Installation
from slack_bolt.async_app import AsyncApp
from typing import Optional, List
from installation_store import SlackMusicInstallationStore
from user_store import SlackMusicUserStore
from models.users import User
from weekly_polls_store import SlackMusicWeeklyPollsStore
from models.weekly_polls import WeeklyPoll, SongInfo, VoteInfo
from spotify_installation_store import SlackSpotifyInstallationStore
import re
from datetime import datetime
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
import json
load_dotenv()


APP_HOST = 'https://darri.ngrok.app'

oauth_settings = AsyncOAuthSettings(
    client_id=os.environ["SLACK_CLIENT_ID"],
    client_secret=os.environ["SLACK_CLIENT_SECRET"],
    scopes=["channels:read", "groups:read", "chat:write"],
    installation_store=SlackMusicInstallationStore(),
)


oauth_flow = AsyncOAuthFlow(
    settings=oauth_settings,
)

app = AsyncApp(
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    oauth_flow=oauth_flow
)

user_store = SlackMusicUserStore()
weekly_polls_store = SlackMusicWeeklyPollsStore()

spotify_installation_store = SlackSpotifyInstallationStore()


from aiohttp import web
import base64

@app.event("team_access_granted")
async def team_access_granted(client, event, logger):
    print("team access granted")
    print("setup things here")

@app.event("team_join")
async def team_joined(client, event, logger):
    print("team joined")
    print("setup things here")

# New functionality
@app.event("app_installed")
async def app_installed(client, event, logger):
  print("app installed")
  print("setup things here")

@app.event("app_mention")
async def event_test(body, say, logger):
    await say("What's up?")

@app.command("/hello-bolt-python")
async def command(ack, body, respond):
    await ack()
    await respond(f"Hi <@{body['user_id']}>!")

async def get_or_create_user(client, team_id: str, user_id: str) -> User:
    app_user = await user_store.get_user(team_id, user_id)
    if app_user is None:
        slack_user_response = await client.users_info(user=user_id)
        app_user = User(**slack_user_response.data['user'])
        await user_store.save_user(team_id, user_id, app_user)
    return app_user

async def get_or_create_weekly_poll(team_id: str, poll_id: str):
    weekly_pool = await weekly_polls_store.get_poll(team_id, poll_id)
    if weekly_pool is None:
        weekly_pool = WeeklyPoll.generate_new_weekly_poll(poll_id)
        await weekly_polls_store.save_poll(team_id, weekly_pool)
    return weekly_pool


async def update_home_tab_view(client, app_user: User, weekly_poll: WeeklyPoll, logger):
    # Check the status of the poll
    poll_status = weekly_poll.status  # Assuming status is an attribute of weekly_poll

    view_blocks = []

    if poll_status == "submissions_open":
        # Show the submission form if the user hasn't submitted a song yet
        if not await user_has_submitted_song(app_user, weekly_poll):
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Submit your song for this week's poll!*"
                }
            })
            view_blocks.append({
                "dispatch_action": True,
                "type": "input",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "submitted_song"
                },
                "label": {
                    "type": "plain_text",
                    "text": "Submit your song here:",
                    "emoji": True
                }
            })
        else:
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*You have already submitted a song for this week's poll!*"
                }
            })
        
        # Show the submissions so far
        submissions = await get_poll_submissions(weekly_poll)

        print("submissions:", submissions)

        view_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Submissions so far:*"
            }
        })

        if len(submissions) == 0:
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No submissions yet."
                }
            })

        else:
            for song_info in submissions:
                view_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":musical_note: *{song_info.title}\n{song_info.artist}"
                    }
                })
# give me a backslash: \
    elif poll_status == "voting_open":
        # Show the voting form if the user hasn't voted yet

        if not await user_has_voted(app_user):
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Vote for your favorite song!*"
                }
            })
        else:
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*You have already voted for this week's poll!*"
                }
            })

        view_blocks.append({
            "type": "divider"
        })

        # Add voting options (example)
        voting_options = await get_voting_options(weekly_poll)

        vote_info = await get_vote_information(weekly_poll)

        for (index, option) in enumerate(voting_options):

            vote_block = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{index}. *{option.title}*\n{option.artist}"
                }
            }

            if not await user_has_voted(app_user):
                vote_block["accessory"] = {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "emoji": True,
                        "text": f"Vote for {index}"
                    },
                    "value": option.id,
                    "action_id": "vote"
                }

            view_blocks.append(vote_block)

            voted_for_this_song_avatars = []
            for vote in vote_info:
                if vote.voted_for == option.id:
                    user = await get_or_create_user(client, app_user.team_id, vote.voted_by)
                    voted_for_this_song_avatars.append({
                        "type": "image",
                        "image_url": user.profile.image_24,
                        "alt_text": user.name
                    })    

            view_blocks.append({
                "type": "context",
                "elements": [
                    *voted_for_this_song_avatars,
                    {
                        "type": "plain_text",
                        "emoji": True,
                        "text": f"{len(voted_for_this_song_avatars)} vote" + ("s" if len(voted_for_this_song_avatars) > 1 or len(voted_for_this_song_avatars) == 0 else "")
                    }
                ]
            })

    elif poll_status == "closed":
        # Show the results
        view_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Poll Results:*"
            }
        })

        voting_options = await get_voting_options(weekly_poll)

        vote_info = await get_vote_information(weekly_poll)

        votes_count = {}
        for vote in vote_info:
            if vote.voted_for in votes_count:
                votes_count[vote.voted_for] += 1
            else:
                votes_count[vote.voted_for] = 1
        
        sorted_votes = sorted(votes_count.items(), key=lambda x: x[1], reverse=True)

        for (index, (song_id, vote_count)) in enumerate(sorted_votes[:3]):
            song_info = weekly_poll.songs[song_id]
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":trophy: *{index + 1}.* {song_info.title}\n{song_info.artist}\nVotes: {vote_count}"
                }
            })
        
        # TODO: Show the playlist link


        

    if app_user.is_admin:
        # Show admin controls
        view_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Admin Controls:*"
            }
        })
        view_blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Change Poll Status"
                    },
                    "action_id": "change_poll_status",
                }
            ]
        })

        spotify_installation = await spotify_installation_store.get_installation(app_user.team_id)

        print("spotify installation:", spotify_installation)

        if spotify_installation is None:
            # install spotify button
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Install Spotify to create playlists"
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Install Spotify"
                    },
                    "action_id": "install_spotify",
                }
            })

        else:
            # show playlist link
            view_blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Spotify Installation found."
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Uninstall Spotify"
                    },
                    "action_id": "uninstall_spotify",
                }
            })

        if await user_has_submitted_song(app_user, weekly_poll):
            view_blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Unsubmit Song"
                        },
                        "action_id": "unsubmit_song",
                    }
                ]
            })
        
        if await user_has_voted(app_user):
            view_blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Unvote"
                        },
                        "action_id": "unvote",
                    }
                ]
            })


    # Publish the view to the Home tab
    try:
        await client.views_publish(
            user_id=app_user.id,
            view={
                "type": "home",
                "callback_id": "home_view",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*Welcome to your _App's Home tab_* :tada:"
                        }
                    },
                    {
                        "type": "divider"
                    },
                    *view_blocks,  # Include the dynamically generated blocks here
                ]
            }
        )

    except Exception as e:
        logger.error(f"Error publishing home tab view: {str(e)}")
        try:
            await client.chat_postMessage(
                channel=app_user.id,
                text="Error publishing home tab view. Please try again later.: " + str(e)
            )
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

@app.event("app_home_opened")
async def update_home_tab(client, event, logger):
    if event.get("tab") != "home":
        return
    
    print("app home opened")

    team_id = event["view"]['team_id']
    user_id = event["user"]

    app_user = await get_or_create_user(client, team_id, user_id)  # type: User
    poll_id = WeeklyPoll.generate_poll_id()
    weekly_poll = await get_or_create_weekly_poll(app_user.team_id, poll_id)

    print("got user:", app_user.id)
    print("got weekly poll:", weekly_poll.poll_id)

    await update_home_tab_view(client, app_user, weekly_poll, logger)

# Helper functions (to be defined)
async def user_has_submitted_song(user: User, poll: WeeklyPoll):
    # Logic to check if the user has submitted a song
    return user.slack_music_config.submitted

async def user_has_voted(user: User):
    # Logic to check if the user has voted
    return user.slack_music_config.voted

async def get_poll_submissions(weekly_poll: WeeklyPoll) -> List[SongInfo]:
    # Logic to retrieve submissions for the poll
    return weekly_poll.songs.values()

async def get_voting_options(weekly_poll: WeeklyPoll) -> List[SongInfo]:
    # Logic to retrieve voting options for the poll
    return weekly_poll.songs.values()  # Assuming songs is a dictionary of SongInfo 

async def get_vote_information(weekly_poll: WeeklyPoll) -> Optional[VoteInfo]:
    # Logic to retrieve vote information for the poll
    return weekly_poll.votes.values()

@app.action("click_me_button")
async def handle_some_action(ack, body, logger):
    await ack()
    logger.info(body)
    print("button clicked")

def is_spotify_track_link(input_string):
    # Regular expression to match the Spotify track URL
    pattern = r"^https://open\.spotify\.com/track/([a-zA-Z0-9]{22})(\?si=[a-zA-Z0-9]+)?$"
    match = re.match(pattern, input_string)
    
    # If a match is found, return the track ID (first capture group)
    if match:
        return match.group(1)  # The track ID is captured here
    return None

# Function to open an error modal
async def show_error_modal(client, trigger_id, error_message, title="Error", close_message="Close"):
    error_view = {
        "type": "modal",
        "title": {"type": "plain_text", "text": title},
        "close": {"type": "plain_text", "text": close_message},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":warning: *Error:* {error_message}"}
            }
        ]
    }
    await client.views_open(trigger_id=trigger_id, view=error_view)

@app.action("change_poll_status")
async def handle_change_poll_status(ack, body, client, logger):
    await ack()
    logger.info(body)
    print("change poll status")

    team_id = body["user"]["team_id"]

    user_id = body["user"]["id"]

    trigger_id = body["trigger_id"]

    app_user = await get_or_create_user(client, team_id, user_id)  # type: User
    

    poll_id = WeeklyPoll.generate_poll_id()

    weekly_poll = await get_or_create_weekly_poll(app_user.team_id, poll_id)

    if not app_user.is_admin:
        print("User is not an admin")
        await show_error_modal(client, trigger_id, "You do not have permission to change the poll status.", title="Permission Denied", close_message="Got it!")
        return
    
    # Logic to change the poll status

    # For example, toggle between "submissions_open" and "voting_open"

    if weekly_poll.status == "submissions_open":
        weekly_poll.status = "voting_open"
    

    elif weekly_poll.status == "voting_open":
        weekly_poll.status = "closed"
    
    elif weekly_poll.status == "closed":
        weekly_poll.status = "submissions_open"

    await weekly_polls_store.save_poll(app_user.team_id, weekly_poll)

    await update_home_tab_view(client, app_user, weekly_poll, logger)

@app.action("unsubmit_song")
async def handle_unsubmit_song(ack, body, client, logger):
    await ack()
    logger.info(body)
    print("unsubmit song")

    team_id = body["user"]["team_id"]

    user_id = body["user"]["id"]

    trigger_id = body["trigger_id"]

    app_user = await get_or_create_user(client, team_id, user_id)

    poll_id = WeeklyPoll.generate_poll_id()

    weekly_poll = await get_or_create_weekly_poll(app_user.team_id, poll_id)

    if not app_user.slack_music_config.submitted:
        print("User has not submitted a song")
        await show_error_modal(client, trigger_id, "You have not submitted a song yet.", title="Not Submitted", close_message="Got it!")
        await update_home_tab_view(client, app_user, weekly_poll, logger)
        return

    app_user.slack_music_config.submitted = False

    await user_store.save_user(team_id, user_id, app_user)

    await update_home_tab_view(client, app_user, weekly_poll, logger)

@app.action("install_spotify")
async def handle_install_spotify(ack, body, client, logger):
    await ack()
    logger.info(body)
    print("unsubmit song")

    team_id = body["user"]["team_id"]

    user_id = body["user"]["id"]

    app_user = await get_or_create_user(client, team_id, user_id)

    # send message with link to install spotify

    spotify_install_link = general_spotify_client.get_install_link(team_id, user_id)

    try:
        await client.chat_postMessage(
            channel=app_user.id,
            text=f"Click [here]({spotify_install_link}) to install Spotify"
        )
    except Exception as e:
        logger.error(f"Error sending Spotify install link: {str(e)}")

@app.action("unvote")
async def handle_unvote(ack, body, client, logger):
    await ack()
    logger.info(body)
    print("unvote")

    team_id = body["user"]["team_id"]

    user_id = body["user"]["id"]

    trigger_id = body["trigger_id"]

    app_user = await get_or_create_user(client, team_id, user_id)

    poll_id = WeeklyPoll.generate_poll_id()

    weekly_poll = await get_or_create_weekly_poll(app_user.team_id, poll_id)

    if not app_user.slack_music_config.voted:
        print("User has not voted")
        await show_error_modal(client, trigger_id, "You have not voted yet.", title="Not Voted", close_message="Got it!")
        await update_home_tab_view(client, app_user, weekly_poll, logger)
        return

    app_user.slack_music_config.voted = False

    await user_store.save_user(team_id, user_id, app_user)

    await update_home_tab_view(client, app_user, weekly_poll, logger)

class SpotifyClient:

    REDIRECT_ENDPOINT = "/install/spotify/callback"

    REDIRECT_URI = f'{APP_HOST}{REDIRECT_ENDPOINT}'  # Make sure this URI is whitelisted in your Spotify app settings
    SCOPES = 'playlist-modify-public,playlist-modify-private'

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = self.get_access_token()

    def get_access_token(self):
        # Logic to retrieve the access token
        url = "https://accounts.spotify.com/api/token"
        payload = {'grant_type': 'client_credentials'}
        response = requests.post(url, data=payload, auth=HTTPBasicAuth(self.client_id, self.client_secret))
        response_data = response.json()
        return response_data['access_token']

    def token_exchange(self, code):
        # Logic to retrieve the access token
        payload = {
            "code": code,
            "redirect_uri": self.REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": generate_auth_header(self.client_id, self.client_secret)
        }
        
        response = requests.post('https://accounts.spotify.com/api/token', data=payload, headers=headers)

        if response.status_code == 200:
            return response.json()  # Successful token response
        else:
            return {"error": response.json().get("error", "unknown_error"), "status": response.status_code}

    def get_song_info(self, track_id):
        # Logic to retrieve song information from the Spotify API
        url = f"https://api.spotify.com/v1/tracks/{track_id}"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = requests.get(url, headers=headers)
        response_data = response.json()
        return response_data
    
    def get_install_link(self, team_id: str, user_id: str):

        state = {
            "team_id": team_id,
            "user_id": user_id
        }

        # encode in some way to decode later
        state_encoded = base64.b64encode(json.dumps(state).encode("utf-8")).decode("utf-8")

        auth_url = (
            f"https://accounts.spotify.com/authorize?client_id={self.client_id}&response_type=code&"
            f"redirect_uri={self.REDIRECT_URI}&scope={self.SCOPES}&state={state_encoded}"
        )

        return auth_url

    
    def create_playlist(self, user_id, playlist_name):
        # Logic to create a new playlist
        url = f"https://api.spotify.com/v1/users/{user_id}/playlists"

    
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", None)
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", None)

general_spotify_client = SpotifyClient(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)


def generate_auth_header(client_id, client_secret):
    """
    Generate the Base64-encoded Authorization header for Spotify API.
    """
    credentials = f"{client_id}:{client_secret}"
    return "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("utf-8")


def handle_token_exchange(code):
    """
    Send a POST request to Spotify to exchange the authorization code for an access token.
    example response:
    {'access_token': 'BQBECTyY_ZlfX...123nhhg', 'token_type': 'Bearer', 'expires_in': 3600, 'refresh_token': 'AQAdXZVao1X_34vOl...5gRmQI5VxuBjunOnSY', 'scope': 'playlist-modify-public'}
    """
    payload = {
        "code": code,
        "redirect_uri": general_spotify_client.REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": generate_auth_header(general_spotify_client.client_id, general_spotify_client.client_secret)
    }
    
    response = requests.post('https://accounts.spotify.com/api/token', data=payload, headers=headers)

    if response.status_code == 200:
        return response.json()  # Successful token response
    else:
        return {"error": response.json().get("error", "unknown_error"), "status": response.status_code}


async def install_spotify_callback(_req: web.Request):

    print("install spotify callback")

    code = _req.query.get("code")

    state = _req.query.get("state")

    print("code:", code)
    print("state:", state)

    if code is None:
        return web.Response(text="Error: Missing code parameter", status=400)
    
    if state is None:
        return web.Response(text="Error: Missing state parameter", status=400)
    
    token_response = general_spotify_client.token_exchange(code)

    if "error" in token_response:
        return web.Response(text=f"Error: {token_response['error']}", status=400)

    print("token response:", token_response)

    state_decoded = base64.b64decode(state).decode("utf-8")

    state_data = json.loads(state_decoded)

    team_id = state_data["team_id"]

    user_id = state_data["user_id"]

    print("team_id:", team_id)

    print("user_id:", user_id)

    access_token = token_response['access_token']
    refresh_token = token_response['refresh_token']
    expires_in = token_response['expires_in']

    await spotify_installation_store.save_installation(team_id, user_id, access_token, refresh_token, expires_in)

    return web.Response(text="Spotify installed successfully")

web_app = app.web_app()
web_app.add_routes([web.get(SpotifyClient.REDIRECT_ENDPOINT, install_spotify_callback)])


async def get_song_info(user_id: str, track_id: str) -> SongInfo:
    # Logic to retrieve song information from the Spotify API
    track_data = general_spotify_client.get_song_info(track_id)
    return SongInfo(
        id=track_id,
        link=f"https://open.spotify.com/track/{track_id}",
        title=track_data['name'],
        artist=", ".join(artist['name'] for artist in track_data['artists']),
        album=track_data['album']['name'],
        image_url=track_data['album']['images'][0]['url'] if track_data['album']['images'] else None,
        submitted_by=user_id
    )

# Define the action handler with a regular expression to match dynamic action IDs
@app.action("vote")
async def handle_vote_action(ack, body, client, logger):
    # Acknowledge the action
    await ack()

    song_id = body["actions"][0]["value"]

    team_id = body["user"]["team_id"]

    user_id = body["user"]["id"]

    app_user = await get_or_create_user(client, team_id, user_id)

    poll_id = WeeklyPoll.generate_poll_id()

    weekly_poll = await get_or_create_weekly_poll(app_user.team_id, poll_id)

    if app_user.slack_music_config.voted:
        print("User has already voted")
        await show_error_modal(client, body["trigger_id"], "You have already voted.", title="Already Voted", close_message="Got it!")
        await update_home_tab_view(client, app_user, weekly_poll, logger)
        return

    # Cast the vote
    weekly_poll.votes[user_id] = VoteInfo(
        voted_for=song_id,
        voted_at=datetime.now(),
        voted_by=user_id
    )

    await weekly_polls_store.save_poll(app_user.team_id, weekly_poll)

    app_user.slack_music_config.voted = True

    await user_store.save_user(team_id, user_id, app_user)

    await update_home_tab_view(client, app_user, weekly_poll, logger)


@app.action("submitted_song")
async def handle_submitted_song(ack, body, client, logger):

    await ack()
    logger.info(body)
    print("song submitted")

    team_id = body["user"]["team_id"]

    user_id = body["user"]["id"]

    trigger_id = body["trigger_id"]

    app_user = await get_or_create_user(client, team_id, user_id) # type: User

    poll_id = WeeklyPoll.generate_poll_id()

    weekly_poll = await get_or_create_weekly_poll(app_user.team_id, poll_id)

    if app_user.slack_music_config.submitted:
        print("User has already submitted a song")
        await show_error_modal(client, trigger_id, "You have already submitted a song for this week's poll.", title="Already Submitted", close_message="Got it!")
        await update_home_tab_view(client, app_user, weekly_poll, logger)

    submitted_song = body["actions"][0]["value"]

    print("User submitted song:", submitted_song)

    # Check if the submitted song is a valid Spotify track link

    track_id = is_spotify_track_link(submitted_song)

    if track_id is None:
        print("Invalid Spotify track link")
        await show_error_modal(client, trigger_id, "Please submit a valid Spotify track link.", title="Invalid Link", close_message="Got it!")
        return

    print("Spotify track ID:", track_id)

    # Add the song to the weekly poll

    song_info = await get_song_info(app_user.id, track_id)

    playlist = await get_weekly_playlist(weekly_poll)

    weekly_poll.songs[track_id] = song_info

    await weekly_polls_store.save_poll(app_user.team_id, weekly_poll)

    # Save the submitted song to the user's profile
    app_user.slack_music_config.submitted = True
    app_user.slack_music_config.submissions.append(track_id)

    await user_store.save_user(team_id, user_id, app_user)

    # Update the Home tab view
    await update_home_tab_view(client, app_user, weekly_poll, logger)



if __name__ == "__main__":
    app.start(3000)
