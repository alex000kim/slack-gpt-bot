import os
import re
import requests
from bs4 import BeautifulSoup
import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
N_CHUNKS_TO_CONCAT_BEFORE_UPDATING = 20

app = App(token=SLACK_BOT_TOKEN)
openai.api_key = OPENAI_API_KEY
    
def extract_url_list(text):
    url_pattern = re.compile(
        r'<(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)>'
    )
    url_list = url_pattern.findall(text)
    return url_list if len(url_list)>0 else None


def extract_text_from_url(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(['script', 'style']):
                script.decompose()
            text = ' '.join(soup.stripped_strings)
            return text
        else:
            print(f"Error: Received a {response.status_code} status code.")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None
    
def augment_user_message(user_message):
    url_list = extract_url_list(user_message)
    if url_list:
        all_url_content = ''
        for url in url_list:
            url_content = extract_text_from_url(url)
            all_url_content = all_url_content + f'\nContent from {url}:\n"""\n{url_content}\n"""'
        user_message = user_message + "\n" + all_url_content
    return user_message

conversations = {}

@app.event("app_mention")
def command_handler(body, context):
    channel_id = body['event']['channel']
    if body['event'].get('thread_ts'):
        thread_ts = body['event']['thread_ts']
    else:
        thread_ts = body['event']['ts']
        
    slack_resp = app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Got your request. Please wait."
            )
    message_ts = slack_resp['message']['ts']
    user_message = body['event']['text']
    print(f'user_message: {user_message}')
    try:
        bot_user_id = context['bot_user_id']
        conversation_id = f"{channel_id}-{thread_ts}"
        user_message = user_message.replace(f'<@{bot_user_id}>', '').strip()
        user_message = augment_user_message(user_message)
        
        if conversation_id not in conversations:
            conversations[conversation_id] = []
        conversations[conversation_id].append({"role": "system", "content": "User has started a conversation."})
        conversations[conversation_id].append({"role": "user", "content": user_message})

        openai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=conversations[conversation_id],
            stream=True)

        response_text = ""
        
        ii = 0
        for chunk in openai_response:
            if chunk.choices[0].delta.get('content'):
                ii = ii + 1
                response_text += chunk.choices[0].delta.content
                if ii > N_CHUNKS_TO_CONCAT_BEFORE_UPDATING:
                    app.client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        text=response_text
                    )
                    ii = 0
            elif chunk.choices[0].finish_reason == 'stop':
                app.client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        text=response_text + "\n\n<EOM>"
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
