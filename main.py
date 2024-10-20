import os
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_bolt.oauth.async_oauth_flow import AsyncOAuthFlow
from slack_bolt.oauth.async_callback_options import DefaultAsyncCallbackOptions
from slack_sdk.oauth.installation_store.models import Installation
from slack_bolt.async_app import AsyncApp
from typing import Optional
from installation_store import SlackMusicInstallationStore
from user_store import SlackMusicUserStore
from models.users import User


oauth_settings = AsyncOAuthSettings(
    client_id=os.environ["SLACK_CLIENT_ID"],
    client_secret=os.environ["SLACK_CLIENT_SECRET"],
    scopes=["channels:read", "groups:read", "chat:write"],
    installation_store=SlackMusicInstallationStore(),
    # state_store=AsyncOAuthStateStore()
)


oauth_flow = AsyncOAuthFlow(
    settings=oauth_settings,
)

app = AsyncApp(
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    oauth_flow=oauth_flow
)

user_store = SlackMusicUserStore()


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

async def get_or_create_user(client, user_id: str):
    app_user = await user_store.get_user(user_id)
    if app_user is None:
        print("User not found in store, fetching from Slack")
        slack_user_response = await client.users_info(user=user_id)
        app_user = User(**slack_user_response.data['user'])
        await user_store.save_user(user_id, app_user)
    return app_user

# New functionality
@app.event("app_home_opened")
async def update_home_tab(client, event, logger):

  app_user = await get_or_create_user(client, event["user"]) # type: User

  try:
    # views.publish is the method that your app uses to push a view to the Home tab
    await client.views_publish(
      # the user that opened your app's app home
      user_id=event["user"],
      # the view object that appears in the app home
      view={
        "type": "home",
        "callback_id": "home_view",

        # body of the view
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
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "This button won't do much for now but you can set up a listener for it using the `actions()` method and passing its unique `action_id`. See an example in the `examples` folder within your Bolt app."
            }
          },
          {
            "type": "actions",
            "elements": [
              {
                "type": "button",
                "action_id": "click_me_button",
                "text": {
                  "type": "plain_text",
                  "text": "Click me!"
                }
              }
            ]
          }
        ]
      }
    )

  except Exception as e:
    logger.error(f"Error publishing home tab: {e}")

@app.action("click_me_button")
async def handle_some_action(ack, body, logger):
    await ack()
    logger.info(body)
    print("button clicked")

if __name__ == "__main__":
    app.start(3000)
