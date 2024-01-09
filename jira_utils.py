from config import get_env_variable
from api_handler import make_jira_request
import logging
import time
import socket

env_variable_names = [
    "JIRA_HOST_ATTRIBUTE_ID", "JIRA_GUESTVM_ATTRIBUTE_ID",
    "JIRA_HOST_STATUS_ATTRIBUTE_ID", "JIRA_GUESTVM_STATUS_ATTRIBUTE_ID",
    "OBJECT_SCHEMA", "HOST_NETWORK_ATTRIBUTE_ID",
    "HOST_SITE_ATTRIBUTE_ID", "HOST_NAME_ATTRIBUTE_ID",
    "GUESTVM_NETWORK_ATTRIBUTE_ID", "GUESTVM_SITE_ATTRIBUTE_ID",
    "GUESTVM_NAME_ATTRIBUTE_ID", "DEVICE_NETWORK_ATTRIBUTE_ID",
    "DEVICE_SITE_ATTRIBUTE_ID", "DEVICE_NAME_ATTRIBUTE_ID",
    "NETWORK_OBJECT_NAME_ATTRIBUTE_ID", "NETWORK_OBJECT_IP4_ATTRIBUTE_ID",
    "OBJECT_TYPE_ID_DICT", "HOST_OS_ATTRIBUTE_ID",
    "GUESTVM_OS_ATTRIBUTE_ID", "HOST_DEVICE_TYPE_ATTRIBUTE_ID",
    "GUESTVM_DEVICE_TYPE_ATTRIBUTE_ID", "DEVICE_DEVICE_TYPE_ATTRIBUTE_ID",
    "HOST_MODEL_ATTRIBUTE_ID", "DEVICE_MODEL_ATTRIBUTE_ID",
    "VIRTUAL_WORKSTATION_ID", "SERVER_ID", "COMPUTER_ID",
    "AP_ID", "CAMERA_ID", "CONTROLLER_ID",
    "FIREWALL_ID", "IMPI_ID", "SWITCH_ID",
    "PDU_ID", "PRINTER_ID", "UPS_ID"
]

# Function to convert string representation to dictionary (for complex types)
def str_to_dict(str_value):
    try:
        return eval(str_value)
    except (SyntaxError, NameError):
        return None

# Iterate over the list and set global variables
for var_name in env_variable_names:
    value = get_env_variable(var_name)
    if var_name == "OBJECT_TYPE_ID_DICT":
        value = str_to_dict(value)
    globals()[var_name] = value

# Create ATTRIBUTE_DISPLAY_DICT using the global variables
ATTRIBUTE_DISPLAY_DICT = {
    "host": [HOST_NAME_ATTRIBUTE_ID, HOST_NETWORK_ATTRIBUTE_ID, HOST_SITE_ATTRIBUTE_ID],
    "virtual guest": [GUESTVM_NAME_ATTRIBUTE_ID, GUESTVM_NETWORK_ATTRIBUTE_ID, GUESTVM_SITE_ATTRIBUTE_ID],
    "device": [DEVICE_NAME_ATTRIBUTE_ID, DEVICE_NETWORK_ATTRIBUTE_ID, DEVICE_SITE_ATTRIBUTE_ID],
}

SERVER_OS = ["CentOS", "Ubuntu", "Server", "Linux"]
COMPUTER_OS = ["Windows 10", "Windows 8.1", "Windows 7"]
AUTH = get_env_variable("JIRA_EMAIL"), get_env_variable("JIRA_TOKEN")

def get_attribute_id(type):
    """
    Returns the attribute ID based on the type.
    """
    return {
        "host": JIRA_HOST_ATTRIBUTE_ID,
        "virtual guest": JIRA_GUESTVM_ATTRIBUTE_ID,
    }.get(type)

def check_attribute(item, attribute_id, backup_location):
    """
    Checks if the given item has the specified attribute set to the backup location.
    """
    return item["objectTypeAttributeId"] == attribute_id and \
        item["objectAttributeValues"][0]["displayValue"] == backup_location

def object_attribute_search(object_key, backup_location, type):
    """
    Check if a specific backup location is already set for an object.
    """
    attribute_id = get_attribute_id(type)
    if not attribute_id:
        logging.error(f"Unknown type: {type}")
        return False

    response = make_jira_request("GET", f"/object/{object_key}/attributes")
    if response:
        for item in response:
            if check_attribute(item, attribute_id, backup_location):
                logging.info(f"Found {backup_location} already set for {object_key}, skipping.")
                return True
    return False

def is_valid_install_status(value, do_not_set_status):
    """
    Checks if the installation status is valid and not in the do_not_set_status list.
    """
    return value["displayValue"].lower() not in do_not_set_status

def install_status_check(object_key, type):
    """
    Checks the installation status of an object.
    """
    attribute_id = get_attribute_id(type)
    if not attribute_id:
        logging.error(f"Unknown type: {type}")
        return False

    response = make_jira_request("GET", f"/object/{object_key}/attributes")
    if response:
        for item in response:
            if item["objectTypeAttributeId"] == attribute_id:
                for value in item["objectAttributeValues"]:
                    logging.info(f"Install value {value['displayValue']}")
                    if is_valid_install_status(value, ["disposed", "retired", "lost-stolen"]):
                        return True
    return False

def object_type_search(hostname):
    # Helper function to search for an object type
    def search_for_object_type(object_type):
        query = {"startAt": "0", "maxResults": "25"}
        payload = {
            "qlQuery": f'objectType = "{object_type}" AND "Name" LIKE "{hostname}" ORDER BY Name ASC'
        }
        data = make_jira_request("POST", "/object/aql", data=payload, params=query)
        if data and "values" in data:
            for value in data["values"]:
                return value["label"], value["id"], object_type.lower()
        return None, None, None

    # Search for Host object type
    label, object_key, object_type = search_for_object_type("Host")
    if label:
        return label, object_key, object_type

    # If not found, search for Virtual Guest object type
    return search_for_object_type("Virtual Guest")



def update_backup_location(object_key, backup_location, type):
    # Determine the attribute ID based on the type
    attribute_id = get_attribute_id(type)
    if not attribute_id:
        logging.error(f"Unknown type: {type}")
        return

    # Prepare the payload
    payload = {
        "attributes": [
            {
                "objectTypeAttributeId": attribute_id,
                "objectAttributeValues": [
                    {
                        "value": backup_location,
                        "displayValue": backup_location,
                        "searchValue": backup_location,
                        "referencedType": "false",
                    }
                ],
            }
        ]
    }

    # Make the API request
    response_data = make_jira_request("PUT", f"/object/{object_key}", data=payload)

    if response_data is not None:
        logging.info(f"Updated location for {object_key} to {backup_location}")
    else:
        logging.error(f"Failed to update location for {object_key}")

def jira_get_objects(object_type: str):
    """
    Retrieves a list of objects from Jira based on the specified object type.

    Args:
        object_type (str): The type of object to retrieve (host, virtual guest, or device).

    Returns:
        list: A list of dictionaries, where each dictionary represents an object.
    """
    object_type_id = OBJECT_TYPE_ID_DICT[object_type]
    attributes_to_display_ids = ATTRIBUTE_DISPLAY_DICT[object_type]
    if object_type == "virtual guest":
        object_type = "Virtual Guest"
    pages = 1
    page = 1
    data_list = []

    while pages >= page:
        payload = {
            "objectTypeId": object_type_id,
            "attributesToDisplay": {
                "attributesToDisplayIds": attributes_to_display_ids
            },
            "page": page,
            "asc": 1,
            "resultsPerPage": 25,
            "includeAttributes": False,
            "objectSchemaId": OBJECT_SCHEMA,
            "qlQuery": f'objectType = "{object_type}"',
        }
        
        data = make_jira_request("POST", "/object/navlist/aql", data=payload)
        
        if data:
            pages = data["pageSize"]
            logging.info(f"Adding page {page} of {pages}")
            page += 1
            data_list.extend(data["objectEntries"])
        else:
            logging.error(f"Failed to retrieve objects for {object_type} failure occurred at {page}, refer to previous errors for api call errors.")
    return data_list

def check_if_device_type_needs_update(object_type: str, object_id: str, device_type: str):
    """
    Checks if the device type of an object in Jira needs to be updated.

    Args:
        object_type (str): The type of object to check (host, virtual guest, or device).
        object_id (str): The ID of the object to check.
        device_type (str): The device type to check for.

    Returns:
        bool: A boolean indicating whether the device type needs to be updated.
    """
    # Determine the attribute ID based on the object type
    attribute_id = {
        "host": HOST_DEVICE_TYPE_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_DEVICE_TYPE_ATTRIBUTE_ID,
        "device": DEVICE_DEVICE_TYPE_ATTRIBUTE_ID,
    }.get(object_type)

    if not attribute_id:
        logging.error(f"Unknown object type: {object_type}")
        return False

    # Make the JIRA API request
    response = make_jira_request("GET", f"/object/{object_id}/attributes")
    if response is None:
        logging.error(f"Failed to retrieve attributes for object {object_id}")
        return False

    for item in response:
        if item["objectTypeAttributeId"] == attribute_id:
            if item["objectAttributeValues"] is not None:
                return any(value["displayValue"] == device_type for value in item["objectAttributeValues"])

    return False  # Return False if the device type is not found or no values present

def jira_set_device_type(object_id: str, object_type: str, device_type: str):
    """
    Updates the device type of an object in Jira.

    Args:
        object_id (str): The ID of the object to update.
        object_type (str): The type of object to update (host, virtual guest, or device).
        device_type (str): The device type to update.

    Returns:
        bool: True if the update is successful, False otherwise.
    """
    attribute_id = {
        "host": HOST_DEVICE_TYPE_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_DEVICE_TYPE_ATTRIBUTE_ID,
    }.get(object_type)

    device_id = {
        "server": SERVER_ID,
        "computer": COMPUTER_ID,
        "virtual workstation": VIRTUAL_WORKSTATION_ID,
    }.get(device_type)

    if not attribute_id or not device_id:
        logging.error(f"Unknown object type or device type: {object_type}, {device_type}")
        return False

    payload = {
        "attributes": [
            {
                "objectTypeAttributeId": attribute_id,
                "objectAttributeValues": [{"value": device_id}],
            }
        ]
    }

    response = make_jira_request("PUT", f"/object/{object_id}", data=payload)
    if response:
        logging.info(f"Updated device type for {object_id}: {device_type}")
        return True
    else:
        logging.error(f"Failed to update device type for {object_id}")
        return False
    
def jira_get_object_os(object_id: str, object_type: str):
    """
    Retrieves the operating system of an object in Jira.

    Args:
        object_id (str): The ID of the object to retrieve.
        object_type (str): The type of object to retrieve (host or virtual guest).

    Returns:
        None or str: The operating system of the object.
    """
    attribute_id = {
        "host": HOST_OS_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_OS_ATTRIBUTE_ID,
    }.get(object_type)

    if not attribute_id:
        logging.error(f"Unknown object type: {object_type}")
        return None

    response = make_jira_request("GET", f"/object/{object_id}/attributes")
    if response:
        for item in response:
            if item["objectTypeAttributeId"] == attribute_id:
                for value in item["objectAttributeValues"]:
                    if "displayValue" in value:
                        return value["displayValue"]

    return None

def decide_device_type_from_os(operating_system, object_type):
    """
    Decides the device type based on the operating system and object type.

    Args:
        operating_system (str): The operating system of the object.
        object_type (str): The type of object (e.g., 'virtual guest').

    Returns:
        str or None: The determined device type, or None if not determinable.
    """
    if object_type == "virtual guest":
        # Check if the OS matches any in the COMPUTER_OS list
        if any(os_name in operating_system for os_name in COMPUTER_OS):
            return "virtual workstation"
    else:
        # Check if the OS matches any in the SERVER_OS list
        if any(os_name in operating_system for os_name in SERVER_OS):
            return "server"
        # Check if the OS matches any in the COMPUTER_OS list
        if any(os_name in operating_system for os_name in COMPUTER_OS):
            return "computer"

    return None

def decide_device_type_from_model(model):
    pass

def jira_get_object_model(object_id, object_type):
    """
    Retrieves the model of an object in Jira.

    Args:
        object_id (str): The ID of the object.
        object_type (str): The type of the object (host or device).

    Returns:
        str or None: The model of the object, or None if not found or an error occurs.
    """
    attribute_id = {
        "host": HOST_MODEL_ATTRIBUTE_ID,
        "device": DEVICE_MODEL_ATTRIBUTE_ID,
    }.get(object_type)

    if not attribute_id:
        logging.error(f"Unknown object type: {object_type}")
        return None

    response = make_jira_request("GET", f"/object/{object_id}/attributes")
    if response:
        for item in response:
            if item["objectTypeAttributeId"] == attribute_id:
                for attribute_value in item["objectAttributeValues"]:
                    if "displayValue" in attribute_value:
                        return attribute_value["displayValue"]

    return None

def jira_get_object_ip_details(object_id, type):
    """
    Retrieves the IP details of an object in Jira.

    Args:
        object_id (str): The ID of the object.
        type (str): The type of the object (host, virtual guest, or device).

    Returns:
        list: A list of IP addresses associated with the object.
    """
    attribute_id = {
        "host": HOST_NETWORK_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_NETWORK_ATTRIBUTE_ID,
        "device": DEVICE_NETWORK_ATTRIBUTE_ID,
    }.get(type)

    if not attribute_id:
        logging.error(f"Unknown type: {type}")
        return []

    response = make_jira_request("GET", f"/object/{object_id}/attributes")
    ip_list = []
    if response:
        for item in response:
            if item["objectTypeAttributeId"] == attribute_id:
                ip_list.extend(value["displayValue"] for value in item["objectAttributeValues"] if "displayValue" in value)

    return ip_list

def decide_site_from_ip(ip_list):
    """
    Decides the site based on the provided list of IP addresses.

    Args:
        ip_list (list): A list of IP addresses.

    Returns:
        tuple: A tuple containing the site name and corresponding IP address, or (None, None) if no match is found.
    """
    site_map = {
        "10": {
            "64": "IND-A",
            "1": "MTL-A", "2": "MTL-A", "3": "MTL-A", "4": "MTL-A", "51": "MTL-A",
            "39": "TEM-A", "33": "TEM-A", "32": "TEM-A", "35": "TEM-A",
            "16": "QUE-A", "18": "QUE-A", "31": "QUE-A",
            "60": "TOR-A", "48": "TOR-A",
            "242": "TWN-A",
        },
        "172": {
            "16": "MTL-A", "17": "MTL-A",
        },
    }

    for ip in ip_list:
        try:
            ip_octets = ip.split(".")

            if len(ip_octets) != 4:
                continue

            first_octet, second_octet = ip_octets[0], ip_octets[1]
            if first_octet in site_map and second_octet in site_map[first_octet]:
                return (site_map[first_octet][second_octet], ip)

        except Exception as e:
            logging.error(f"Failed to parse IP: {ip}. Error: {e}")

    return (None, None)

def jira_set_site(object_id, object_type, site):
    """
    Updates the site of an object in Jira.

    Args:
        object_id (str): The ID of the object.
        object_type (str): The type of object (host, virtual guest, or device).
        site (str): The site to update.

    Returns:
        bool: True if the update is successful, False otherwise.
    """
    attribute_id = {
        "host": HOST_SITE_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_SITE_ATTRIBUTE_ID,
        "device": DEVICE_SITE_ATTRIBUTE_ID,
    }.get(object_type)

    site_object_id = {
        "MTL-A": "50",
        "TEM-A": "54",
        "QUE-A": "52",
        "TOR-A": "55",
        "IND-A": "49",
        "TWN-A": "56",
    }.get(site)

    if not attribute_id or not site_object_id:
        logging.error(f"Unknown object type or site: {object_type}, {site}")
        return False

    payload = {
        "attributes": [
            {
                "objectTypeAttributeId": attribute_id,
                "objectAttributeValues": [{"value": site_object_id}],
            }
        ]
    }

    response = make_jira_request("PUT", f"/object/{object_id}", data=payload)
    if response:
        logging.info(f"Updated Site for {object_id}: {site}")
        return True
    else:
        logging.error(f"Failed to update Site for {object_id}")
        return False

def get_host_name(object_id, type):
    """
    Retrieves the hostname of an object in Jira.

    Args:
        object_id (str): The ID of the object.
        type (str): The type of object (host, virtual guest, or device).

    Returns:
        str or None: The hostname of the object, or None if not found or an error occurs.
    """
    attribute_id = {
        "host": HOST_NAME_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_NAME_ATTRIBUTE_ID,
        "device": DEVICE_NAME_ATTRIBUTE_ID,
    }.get(type)

    if not attribute_id:
        logging.error(f"Unknown type: {type}")
        return None

    response = make_jira_request("GET", f"/object/{object_id}/attributes")
    if response:
        for item in response:
            if item["objectTypeAttributeId"] == attribute_id:
                for attribute_value in item["objectAttributeValues"]:
                    if "value" in attribute_value:
                        return attribute_value["value"]

    logging.info(f"Failed to retrieve hostname for {object_id}")
    return None


def get_ip_address(host_name):
    """
    Retrieves the IP address for a given hostname.

    Args:
        host_name (str): The hostname for which to retrieve the IP address.

    Returns:
        str or None: The IP address of the hostname, or None if not found or an error occurs.
    """
    max_retries = 5  # Maximum number of retries
    wait_time = 2    # Time to wait between retries (in seconds)

    for attempt in range(max_retries):
        try:
            return socket.gethostbyname(host_name)
        except socket.gaierror as e:
            if attempt < max_retries - 1:
                logging.info(f"Attempt {attempt + 1} failed for {host_name}, retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error(f"Failed to retrieve IP address for {host_name} after {max_retries} attempts: {e}")
                return None

def check_if_site_needs_update(object_type, object_id, site):
    """
    Checks if the site attribute of an object in Jira needs to be updated.

    Args:
        object_type (str): The type of object (host, virtual guest, or device).
        object_id (str): The ID of the object.
        site (str): The site to compare.

    Returns:
        bool: True if the site needs to be updated, False otherwise.
    """
    attribute_id = {
        "host": HOST_SITE_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_SITE_ATTRIBUTE_ID,
        "device": DEVICE_SITE_ATTRIBUTE_ID,
    }.get(object_type)

    if not attribute_id:
        logging.error(f"Unknown object type: {object_type}")
        return False

    response = make_jira_request("GET", f"/object/{object_id}/attributes")
    if response:
        for item in response:
            if item["objectTypeAttributeId"] == attribute_id:
                for value in item["objectAttributeValues"]:
                    if value.get("displayValue") == site:
                        return True

    return False

def jira_set_ip_address(object_type, object_id, ip_address):
    attribute_id = {
        "host": HOST_NETWORK_ATTRIBUTE_ID,
        "virtual guest": GUESTVM_NETWORK_ATTRIBUTE_ID,
        "device": DEVICE_NETWORK_ATTRIBUTE_ID,
    }.get(object_type)

    object_type_id = "36"

    if not attribute_id:
        logging.error(f"Unknown object type: {object_type}")
        return

    # Create IP Network Object
    payload = {
        "objectTypeId": object_type_id,
        "attributes": [
            {"objectTypeAttributeId": NETWORK_OBJECT_NAME_ATTRIBUTE_ID, "objectAttributeValues": [{"value": ip_address}]},
            {"objectTypeAttributeId": NETWORK_OBJECT_IP4_ATTRIBUTE_ID, "objectAttributeValues": [{"value": ip_address}]},
        ]
    }

    response = make_jira_request("POST", "/object/create", data=payload)
    if response and response.status_code == 201:
        logging.info(f"Created network object for {ip_address}")
        network_object_id = response["id"]
    else:
        logging.error(f"Failed to create network object for {ip_address}")
        return

    # Add IP Network object to object
    payload = {
        "attributes": [
            {"objectTypeAttributeId": attribute_id, "objectAttributeValues": [{"value": network_object_id}]}
        ]
    }

    response = make_jira_request("PUT", f"/object/{object_id}", data=payload)
    if response and response.status_code == 200:
        logging.info(f"Updated IP for {object_id}: {ip_address}")
    else:
        logging.error(f"Failed to update IP for {object_id}: {ip_address}")

