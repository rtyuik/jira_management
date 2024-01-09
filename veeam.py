from config import get_env_variable
import base64
import requests
import logging
from bs4 import BeautifulSoup
import re
import json

def get_and_encode_password(env_name):
    """
    Retrieves a password from an environment variable and encodes it in Base64.

    Args:
        env_name (str): The name of the environment variable storing the password.

    Returns:
        str: The Base64 encoded password.

    Raises:
        ValueError: If the environment variable is not set or the password is not ASCII encodable.
    """
    password = get_env_variable(env_name)
    if password is None:
        raise ValueError(f"Password environment variable '{env_name}' is not set.")

    try:
        veeam_pass_bytes = password.encode("ascii")
        return base64.b64encode(veeam_pass_bytes).decode('ascii')
    except UnicodeEncodeError:
        raise ValueError(f"Password contained non-ASCII characters and could not be encoded.")

# Constants
VEEAM_URL = get_env_variable("VEEAM_URL", "default_url_if_not_set")
VEEAM_USERNAME = get_env_variable("VEEAM_USERNAME")
VEEAM_PASSWORD = get_and_encode_password("VEEAM_PASSWORD")

LOGIN_URL = VEEAM_URL + "/api/Login/LoginByPassword"
REPORT_URL = VEEAM_URL + "/api/Licensing/CreateMonthlyReportPreview"
HEADERS = {
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept-Encoding": "gzip, deflate, br",
}

def login_to_veeam(username, password):
    """
    Log in to the Veeam service and return the session object.
    """
    with requests.Session() as client:
        response = client.post(
            LOGIN_URL, headers=HEADERS, verify=False, data={"username": username, "password": password}
        )
        parsed_content = json.loads(response.content.decode("utf-8"))
        if parsed_content.get("success"):
            logging.info(f"Connected to Veeam as: {username}")
            return client
        else:
            logging.error(f"Failed to connect to Veeam: {parsed_content.get('errorMessage')}")
            return None

def get_csrf_token(client):
    """
    Retrieve the CSRF token from the Veeam home page.
    """
    home_page = client.get(VEEAM_URL, headers=HEADERS, verify=False, allow_redirects=False)
    soup = BeautifulSoup(home_page.text, "html.parser")
    script_tag = soup.find("script", string=re.compile("CSRFToken"))
    csrf_token = re.search(r"var CSRFToken = '(.*?)';", script_tag.string).group(1)
    logging.info(f"CSRF Token: {csrf_token}")
    return csrf_token

def get_backup_report(client, csrf_token):
    """
    Get the backup report from Veeam.
    """
    headers = HEADERS.copy()
    headers["X-Csrf-Token"] = csrf_token
    headers["content-type"] = ""
    cookie = client.cookies.get_dict()
    headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in cookie.items()])
    
    export_response = client.post(REPORT_URL, headers=headers, verify=False)
    return BeautifulSoup(export_response.text, "html.parser")

def find_tables_between_tags(start_tag, end_tag_name="p"):
    """Find all tables between the start tag and the next occurrence of end_tag_name."""
    tables = []
    current_tag = start_tag.find_next()
    while current_tag and current_tag.name != end_tag_name:
        if current_tag.name == "table":
            tables.append(current_tag)
        current_tag = current_tag.find_next()
    return tables

def find_tables_until_end(tag):
    """Find all tables after the given tag until the end of the document."""
    tables = []
    current_tag = tag.find_next()
    while current_tag:
        if current_tag.name == "table":
            tables.append(current_tag)
        current_tag = current_tag.find_next()
    return tables

def veeam_get_backup_report():
    retry_count = 0
    while retry_count <= 3:
        try:
            client = login_to_veeam(VEEAM_USERNAME, VEEAM_PASSWORD)
            if not client:
                return None

            csrf_token = get_csrf_token(client)
            soup = get_backup_report(client, csrf_token)
            server_names = [
                tag.get_text(strip=True).split(" ")[0]
                for tag in soup.find_all("p")
            ]
            logging.info(
                f"parced server names from Veeam Report: {server_names}"
            )
            final_backup_locations = {}
            for index, server_name in enumerate(server_names):
                server_tag = soup.find("p", string=lambda text: server_name in text)
                if not server_tag:
                    continue
                if index == len(server_names) - 1:
                    tables = find_tables_until_end(server_tag)
                else:
                    tables = find_tables_between_tags(server_tag)

                for vm_table in tables:
                    for row in vm_table.find_all("tr")[1:]:  # Skip the header row
                        vm_name_cell = row.find("td")
                        if vm_name_cell:
                            vm_name = vm_name_cell.get_text(strip=True).lower().replace(".hypertec-group.com", "")
                            final_backup_locations[vm_name] = server_name
            return final_backup_locations

        except Exception as e:
            logging.error(f"Failed to get Veeam Report List with exception: \n {e}")
            retry_count += 1
    
    return None