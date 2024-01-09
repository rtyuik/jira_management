import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def compose_email(subject, body):
    subject = f"Jira Assets - Set Backup Locations Automation {subject}"
    body = (
        "<html><body>"
        + f"<div><strong>Jira Assets - Set Backup Locations Automation Completed</strong></div> <div style='line-height: 140%; text-align: left; word-wrap: break-word;'><p style='font-size: 14px; line-height: 140%;'>{body}</p></div>"
        + "</body></html>"
    )
    return (subject, body)

def send_email(sender_email, subject, body, user, log_file_path=None):
    try:
        server = smtplib.SMTP("mail1.hypertec-group.com")
        mail = MIMEMultipart()
        mail["Subject"] = subject
        mail["From"] = sender_email
        mail["To"] = user
        message_string = MIMEText(body, "html")
        mail.attach(message_string)
        # If a log file path is provided, attach it to the email
        if log_file_path:
            with open(log_file_path, "rb") as attachment:
                # Create a MIMEBase object
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())

                # Encode the payload in base64
                encoders.encode_base64(part)

                # Add appropriate headers for the attachment
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {log_file_path.split('/')[-1]}",
                )

                mail.attach(part)

        server.sendmail(sender_email, user, mail.as_string())
        server.quit()
        return True
    except Exception as e:
        return e


