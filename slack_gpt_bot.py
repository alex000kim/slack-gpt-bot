import openai
import os
from json_logger_stdout import json_std_logger
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from collections import namedtuple

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

from utils import (N_CHUNKS_TO_CONCAT_BEFORE_UPDATING, OPENAI_API_KEY,
                   SLACK_APP_TOKEN, SLACK_BOT_TOKEN, WAIT_MESSAGE,
                   num_tokens_from_messages, process_conversation_history,
                   update_chat)

app = App(token=SLACK_BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

def get_conversation_history(channel_id, thread_ts):
    return app.client.conversations_replies(
        channel=channel_id,
        ts=thread_ts,
        inclusive=True
    )

User = namedtuple('User', ('username', 'display_name', 'first_name', 'last_name', 'email'))
'''
This uses https://api.slack.com/methods/users.profile.get
'''
def get_user_information(user_id):
        result = app.client.users_info(
            user=user_id
        )

        return User(result['user']['name'], 
                result['user']['profile']['display_name'],
                result['user']['profile']['first_name'],
                result['user']['profile']['last_name'],
                result['user']['profile']['email'])

def build_personalized_wait_message(first_name):
    return "Hi " + first_name +"! " + "I got your request, please wait while I ask the wizard..."

@app.event("app_mention")
def command_handler(body, context):
    try:
        json_std_logger._setParams(
            body=body,
            context=context
        )
        json_std_logger.debug('arguments') 

        channel_id = body['event']['channel']
        thread_ts = body['event'].get('thread_ts', body['event']['ts'])
        bot_user_id = context['bot_user_id']
        user_id = context['user_id']

        user = get_user_information(user_id)

        if channel_id != 'C057NBLL2G4': #lock to test channel for beta
            slack_resp = app.client.chat_postMessage( 
                channel=channel_id,
                thread_ts=thread_ts,
                text="Our apologies, however the Beta ChatGPT bot is not allowed outside of the beta-slack-chatgpt-bot channel"
            )
            return

        slack_resp = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=build_personalized_wait_message(user.first_name)
        )

        reply_message_ts = slack_resp['message']['ts']
        conversation_history = get_conversation_history(channel_id, thread_ts)
        messages = process_conversation_history(conversation_history, bot_user_id)
        num_tokens = num_tokens_from_messages(messages)
        
        openai_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            stream=True,
            max_tokens=2048
        )
        
        response_text = ""
        ii = 0
        for chunk in openai_response:
            if chunk.choices[0].delta.get('content'):
                ii = ii + 1
                response_text += chunk.choices[0].delta.content
                if ii > N_CHUNKS_TO_CONCAT_BEFORE_UPDATING:
                    # outgoing_logger.info(f'response: {response_text}')
                    update_chat(app, channel_id, reply_message_ts, response_text)
                    ii = 0
            elif chunk.choices[0].finish_reason == 'stop':
                # outgoing_logger.info(f'response: {response_text}')
                update_chat(app, channel_id, reply_message_ts, response_text)

        json_std_logger._setParams(
            token_count=num_tokens,
            channel_id=channel_id, 
            user=user.username, 
            email=user.email,
            request=messages[1:],   #field 0 is something that slack adds that we don't need
            response=response_text
        )
        json_std_logger.info('RequestResponse')
    
    except Exception as e:
        print(f"Error: {e}")
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"I can't provide a response. Encountered an error:\n`\n{e}\n`")


if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
