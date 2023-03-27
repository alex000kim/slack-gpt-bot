import os

import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from utils import augment_user_message, WAIT_MESSAGE, N_CHUNKS_TO_CONCAT_BEFORE_UPDATING

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
            text=WAIT_MESSAGE
            )
        reply_message_ts = slack_resp['message']['ts']
        conversation_history = app.client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            inclusive=True
        )
        # exclude the last message by bot about waiting
        conversation_messages = conversation_history['messages'][:-1]
        messages = [{"role": "system", "content": "User has started a conversation."}]
        for i, message in enumerate(conversation_messages):
            message_text = message['text']
            role = "assistant" if message['user'] == bot_user_id else "user"
            if i == len(conversation_messages) - 1:
                # last message is the user's message augemented with contents from urls
                message_text = augment_user_message(message_text)
            cond = (f'<@{bot_user_id}>' in message_text) or (message['user'] == bot_user_id)
            if cond:
                message_text = message_text.replace(f'<@{bot_user_id}>', '').strip()
                messages.append({"role": role, "content": message_text})
            
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
