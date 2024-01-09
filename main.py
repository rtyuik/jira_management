from logger import setup_logging
from config import get_local_dir, get_env_variable
from email_handler import send_email, compose_email
from jira_utils import *
from veeam import veeam_get_backup_report
import logging
import schedule
import time
import sys

# Constants
LOG_FILE = get_local_dir() + "/log.log"
SENDER_EMAIL = get_env_variable("SENDER_EMAIL")
SEND_TO_EMAIL = get_env_variable("SEND_TO_EMAIL")

def main():
    """
    Main function.
    """
    object_types = ["host", "device", "virtual guest"]
    setup_logging(LOG_FILE, logging.DEBUG)
    logging.info("Started logging...")
    # logging.info("Starting Veeam Backup Location Update")
    # logging.info("grabbing backup locations from Veeam Report")
    # report = veeam_get_backup_report()
    # if report is None:
    #     logging.info("No backup locations found from Veeam")
    #     sys.exit()

    # logging.info("Finished grabbing backup locations from Veeam Report")
    # failed_list = []
    # for vm_name in report:
    #     logging.info(vm_name)
    #     process_vm(vm_name, report, failed_list)

    # prepare_and_send_email(failed_list)
    # logging.info("Finished sending emails")
    logging.info("Starting Site Location Update Schedule")
    for object_type in object_types:
        logging.info(f"Processing {object_type} objects")
        jira_update_site_location(object_type)


def process_vm(vm_name, report, failed_list):
    try:
        label, object_key, type = object_type_search(vm_name)
        if label is not None:
            logging.info(f"Label: {label}, ObjectKey: {object_key}")
            install_status = install_status_check(object_key, type)
            if install_status:
                backup_location_set = object_attribute_search(object_key, report[vm_name], type)
                if not backup_location_set:
                    logging.info(f"Label: {label}, ObjectKey: {object_key}, Backup Location: {report[vm_name]}")
                    update_backup_location(object_key, report[vm_name], type)
        else:
            logging.info(f"{vm_name} does not exist, adding to failed list")
            failed_list.append(vm_name)
    except Exception as e:
        logging.info(f"Error processing VM {vm_name}: {e}")
        failed_list.append(vm_name)

def update_site_for_object(object_id, object_type, object_ip_list):
    host_site, ip_used = decide_site_from_ip(object_ip_list)
    if host_site is not None:
        logging.info(f"{host_site} decided for {object_id} from {ip_used}")
        site_set = check_if_site_needs_update(object_type, object_id, host_site)
        if not site_set:
            jira_set_site(object_id, object_type, host_site)
        else:
            logging.info(f"Site already set for {object_id}")

def update_device_type_for_object(object_id, object_type, operating_system):
    device_type = decide_device_type_from_os(operating_system, object_type)
    if device_type is not None:
        logging.info(f"{device_type} decided for {object_id}")
        device_type_set = check_if_device_type_needs_update(object_type, object_id, device_type)
        if not device_type_set:
            jira_set_device_type(object_id, object_type, device_type)
        else:
            logging.info(f"Device type already set for {object_id}")

def jira_update_site_location(object_type):
    object_data_list = jira_get_objects(object_type)
    for object_data in object_data_list:

        object_id = object_data["id"]
        host_name = object_data["label"]
        logging.info(f"Working on {object_id}, {host_name}")

        # Update IP Address
        object_ip_list = jira_get_object_ip_details(object_id, object_type)
        if not object_ip_list:
            logging.info(f"No IP set in jira for {object_id}, getting IP from hostname")
            ip_address = get_ip_address(host_name)
            if ip_address:
                logging.info(f"Found IP: {ip_address}")
                object_ip_list.append(ip_address)
                jira_set_ip_address(object_type, object_id, ip_address)

        # Update Site
        if object_ip_list:
            update_site_for_object(object_id, object_type, object_ip_list)
        else:
            logging.info(f"Failed to decide site for {object_id} from {object_ip_list}")

        # Update Device Type
        if object_type in ["host", "virtual guest"]:
            operating_system = jira_get_object_os(object_id, object_type)
            if operating_system:
                update_device_type_for_object(object_id, object_type, operating_system)
        elif object_type == "device":
            model = jira_get_object_model(object_id, object_type)
            if model:
                update_device_type_for_object(object_id, object_type, model)

    logging.info(f"Finished setting site for all {object_type} objects")

def prepare_and_send_email(failed_list):
    if failed_list:
        email_subject = "with Failures"
        email_body = f"These hosts failed to update because they could not be found in Jira Assets:\n{failed_list}"
    else:
        email_subject = "with Success"
        email_body = "All backup locations were updated successfully"

    composed_subject, composed_body = compose_email(email_subject, email_body)
    result = send_email(SENDER_EMAIL, composed_subject, composed_body, SEND_TO_EMAIL, LOG_FILE)
    if result:
        logging.info("Finished sending email")
    else:
        logging.error(f"Failed to send email. \n {result}")


if __name__ == "__main__":
    main()
    # schedule.every().sunday.at("02:00").do(main)
    # while True:
    #     schedule.run_pending()
    #     time.sleep(1)

