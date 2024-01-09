import requests
from requests.auth import HTTPBasicAuth
import json
from config import get_env_variable
import logging
import time

JIRA_URL = get_env_variable("JIRA_URL")
AUTH = get_env_variable("JIRA_EMAIL"), get_env_variable("JIRA_TOKEN")
MAX_RETRIES = 5
RETRY_WAIT_TIME = 2

def make_jira_request(method, endpoint, data=None, params=None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    url = JIRA_URL + endpoint
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                data=json.dumps(data) if data else None,
                params=params,
                auth=HTTPBasicAuth(AUTH[0], AUTH[1]),
            )
            response.raise_for_status()
            return json.loads(response.text)
        except requests.RequestException as e:
            logging.error(f"JIRA API request failed: {e}")
            if attempt < MAX_RETRIES - 1:
                logging.info(f"Attempt {attempt + 1} failed, retrying in {RETRY_WAIT_TIME} seconds...")
                time.sleep(RETRY_WAIT_TIME)
            else:
                logging.error(f"JIRA API request failed after {MAX_RETRIES} attempts: {e}")
                return None
