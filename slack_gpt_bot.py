import os

import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from utils import augment_user_message

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
N_CHUNKS_TO_CONCAT_BEFORE_UPDATING = 20

app = App(token=SLACK_BOT_TOKEN)
openai.api_key = OPENAI_API_KEY
    

@app.event("app_mention")
def command_handler(body, context):
    try:
        channel_id = body['event']['channel']
        thread_ts = body['event'].get('thread_ts', body['event']['ts'])
        bot_user_id = context['bot_user_id']

        slack_resp = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Got your request. Please wait."
            )
        reply_message_ts = slack_resp['message']['ts']

        user_message = body['event']['text'].replace(f'<@{bot_user_id}>', '').strip()
        user_message = augment_user_message(user_message)
        
        conversation_history = app.client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            inclusive=True
        )

        messages = [{"role": "system", "content": "User has started a conversation."}]
        for message in conversation_history['messages']:
            role = "assistant" if message['user'] == bot_user_id else "user"
            messages.append({"role": role, "content": message['text'].replace(f'<@{bot_user_id}>', '').strip()})
            
        openai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            stream=True
        )

        response_text = ""
        ii = 0
        for chunk in openai_response:
            if chunk.choices[0].delta.get('content'):
                ii = ii + 1
                response_text += chunk.choices[0].delta.content
                if ii > N_CHUNKS_TO_CONCAT_BEFORE_UPDATING:
                    app.client.chat_update(
                        channel=channel_id,
                        ts=reply_message_ts,
                        text=response_text
                    )
                    ii = 0
            elif chunk.choices[0].finish_reason == 'stop':
                app.client.chat_update(
                    channel=channel_id,
                    ts=reply_message_ts,
                    text=response_text
                )
        
    except Exception as e:
        print(f"Error: {e}")
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"I can't provide a response. Encountered an error:\n```\n{e}\n```"
            )

if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
