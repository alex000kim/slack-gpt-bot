import re

import requests
from bs4 import BeautifulSoup

WAIT_MESSAGE = "Got your request. Please wait."
N_CHUNKS_TO_CONCAT_BEFORE_UPDATING = 20


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