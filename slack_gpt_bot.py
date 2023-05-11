import openai
import os
import logging
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from collections import namedtuple

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('slack-gpt-bot')

incoming_logger = logging.getLogger('incoming')
incoming_handler = logging.FileHandler('incoming.log')
incoming_logger.addHandler(incoming_handler)

outgoing_logger = logging.getLogger('outgoing')
outgoing_handler = logging.FileHandler('outgoing.log')
outgoing_logger.addHandler(outgoing_handler)

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

from utils import (N_CHUNKS_TO_CONCAT_BEFORE_UPDATING, OPENAI_API_KEY,
                   SLACK_APP_TOKEN, SLACK_BOT_TOKEN, WAIT_MESSAGE,
                   num_tokens_from_messages, process_conversation_history,
                   update_chat)

app = App(token=SLACK_BOT_TOKEN, logger=incoming_logger)
openai.api_key = OPENAI_API_KEY


def get_conversation_history(channel_id, thread_ts):
    return app.client.conversations_replies(
        channel=channel_id,
        ts=thread_ts,
        inclusive=True
    )


User = namedtuple('User', ('username', 'display_name', 'first_name', 'last_name'))
def get_user_information(user_id):
        result = app.client.users_info(
            user=user_id
        )

        return User(result['user']['name'], 
                result['user']['profile']['display_name'],
                result['user']['profile']['first_name'],
                result['user']['profile']['last_name'])

def build_personalized_wait_message(first_name):
    return "Hi " + first_name +"! " + "I got your request, please wait while I ask the wizard..."

@app.event("app_mention")
def command_handler(body, context):
    try:
        logger.debug(f'body: {body}')
        logger.debug(f'context: {context}')

        channel_id = body['event']['channel']
        thread_ts = body['event'].get('thread_ts', body['event']['ts'])
        bot_user_id = context['bot_user_id']
        user_id = context['user_id']

        user = get_user_information(user_id)

        slack_resp = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=build_personalized_wait_message(user.first_name)
        )

        reply_message_ts = slack_resp['message']['ts']
        conversation_history = get_conversation_history(channel_id, thread_ts)
        messages = process_conversation_history(conversation_history, bot_user_id)
        num_tokens = num_tokens_from_messages(messages)
        print(f"Number of tokens: {num_tokens}")
        logger.info(f'Number of tokens: {num_tokens}')
        logger.info(f'Channel ID:{channel_id}:, User: {user.username}, message: {messages}')

        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            stream=True,
            max_tokens=2048
        )
        
        response_text = ""
        ii = 0
        outgoing_logger.info(f'Channel ID:{channel_id}:, User ID: {bot_user_id}, message: {messages}')
        for chunk in openai_response:
            if chunk.choices[0].delta.get('content'):
                ii = ii + 1
                response_text += chunk.choices[0].delta.content
                if ii > N_CHUNKS_TO_CONCAT_BEFORE_UPDATING:
                    outgoing_logger.info(f'response: {response_text}')
                    update_chat(app, channel_id, reply_message_ts, response_text)
                    ii = 0
            elif chunk.choices[0].finish_reason == 'stop':
                outgoing_logger.info(f'response: {response_text}')
                update_chat(app, channel_id, reply_message_ts, response_text)
    except Exception as e:
        print(f"Error: {e}")
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"I can't provide a response. Encountered an error:\n`\n{e}\n`")


if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
