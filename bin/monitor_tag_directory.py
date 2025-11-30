#!/usr/bin/python3 -u

import os
import time
import glob
import datetime
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

# --- Configuration ---
# The directory to monitor (using /dev/shm as requested)
MONITOR_DIR = "/dev/shm"
# The file pattern to look for
FILE_PATTERN = "*.tag"
# How often (in seconds) to check the directory
POLL_INTERVAL_SECONDS = 5
# ---------------------

def process_tag_file(filepath):
    """
    Reads the content of a file into a variable and then deletes the file.

    :param filepath: The full path to the .tag file.
    :return: The content of the file (str) or None if an error occurred.
    """
    file_content = None
    print(f"--- Found file: {filepath} ---")

    try:
        # 1. Read the contents into a variable
        with open(filepath, 'r') as f:
            file_content = f.read()

    except FileNotFoundError:
        # Handle the unlikely case where the file is deleted between glob and open
        print(f"Error: File not found during reading (might have been deleted): {filepath}")
        return None
    except IOError as e:
        print(f"Error reading file {filepath}: {e}")
        return None

    # 2. Delete the file after processing
    # Note: It's important to delete the file to prevent reprocessing it on the next loop iteration.
    try:
        os.remove(filepath)
        print(f"Successfully deleted file: {filepath}")
    except OSError as e:
        print(f"Error deleting file {filepath}: {e}")

    return file_content.strip()

def monitor_directory():
    """
    The main monitoring loop.
    """
    print(f"Starting directory monitor...")
    print(f"Target Directory: {MONITOR_DIR}")
    print(f"Looking for files: {FILE_PATTERN}")
    print(f"Poll Interval: {POLL_INTERVAL_SECONDS} seconds")
    print("-" * 50)

    # Main loop that runs indefinitely
    while True:
        # Construct the full search path
        search_path = os.path.join(MONITOR_DIR, FILE_PATTERN)

        # Use glob to find all files matching the pattern
        tag_files = glob.glob(search_path)

        if tag_files:
            print(f"\n[SCAN] Found {len(tag_files)} new .tag file(s) to process.")

            # Files will be emitted if all are older than X
            emit = False

            # Process each found file
            for file_path in tag_files:
                # Get file's creation time
                creation_timestamp = os.path.getctime(file_path)

                if (time.time() - creation_timestamp) < 300:
                    emit = False
                else:
                    emit = True


            # All files are older
            # Assemble a message and send it out
            if emit:
                body = """
                <html>
                <body>
                  <table cellspacing="0" cellpadding="5" border="5" width="600" style="width: 600px; border-collapse: collapse; border: 5px solid #cccccc;">
                    <tr><td colspan="2" style="background-color: #0b4f8a; color: #ffffff; padding: 10px; font-family: Arial, sans-serif; font-size: 16px; text-align: center; border: 5px solid #cccccc;"><b>AEI Tag Report</b></td></tr>
                    <tr>
                      <th width="50%" style="width: 50%; background-color: #337ab7; color: #ffffff; padding: 10px; font-family: Arial, sans-serif; font-size: 16px; text-align: left; border: 5px solid #cccccc;">Date and Time</th>
                      <th width="50%" style="width: 50%; background-color: #337ab7; color: #ffffff; padding: 10px; font-family: Arial, sans-serif; font-size: 16px; text-align: left; border: 5px solid #cccccc;">AEI Tag</th>
                    </tr>
                """

                total_tags = 0
                string_time = ''

                for file_path in tag_files:

                    # The file content is read and stored here,
                    # though we only print it in this example.
                    creation_timestamp = os.path.getctime(file_path)
                    processed_content = process_tag_file(file_path)
                    string_time = datetime.datetime.fromtimestamp(creation_timestamp).strftime('%Y-%m-%d %H:%M:%S')

                    # You can use the 'processed_content' variable here if needed,
                    # e.g., send it to a database or trigger another action.
                    if processed_content is not None:
                        # Example of using the content variable (just printing type/length)
                        body += f"<tr><td style=\"padding: 10px; font-family: Arial, sans-serif; font-size: 14px; color: #333333; border: 5px solid #cccccc;\">{string_time}</td><td style=\"padding: 10px; font-family: Arial, sans-serif; font-size: 14px; color: #333333; border: 5px solid #cccccc;\">{processed_content}</td></tr>"
                        total_tags += 1

                body += f"""
                    <tr><td colspan="2" style="background-color: #eeeeee; color: #000000; padding: 10px; font-family: Arial, sans-serif; font-size: 12px; text-align: center; border: 5px solid #cccccc;">&copy; 2025 LUCEON LLC. Generated on {string_time}. Tag count: {total_tags}.</td></tr>
                  </table>
                </body>
                </html>
                """

                print(body)

                # Send email out
                for i in range(5):
                    now = datetime.datetime.now()
                    string_time = now.strftime("%Y-%m-%d %H:%M")
                    sent = send_outlook_email("from@from.com", "XXXXXXXXXXX", "to@to.com", f"AEI Tag Report: {string_time}", strip_html_tags_regex(body), body)

                    if sent:
                        break

                    time.sleep(10*i)


        else:
            print(f"[SCAN] No {FILE_PATTERN} files found. Waiting...")

        # Wait before checking the directory again
        time.sleep(POLL_INTERVAL_SECONDS)

def strip_html_tags_regex(html_string: str) -> str:
    """
    Strips HTML tags from a string using a simple regular expression.

    NOTE: This method is fast but is not robust for complex, nested, 
    or malformed HTML. For production code, consider the HTMLParser method.

    :param html_string: The input string potentially containing HTML tags.
    :return: The string with HTML tags removed.
    """
    # Regex to find anything enclosed in < and >
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html_string)

def send_outlook_email(sender_email, sender_password, recipient_email, subject, body_text, body_html=None):
    """
    Sends an email using Outlook.com / Office 365 SMTP servers.

    Args:
        sender_email (str): Your Outlook/Hotmail/Live email address.
        sender_password (str): Your App Password (recommended) or login password.
        recipient_email (str): The email address of the receiver.
        subject (str): The subject line of the email.
        body_text (str): The plain text body of the email.
        body_html (str, optional): The HTML body of the email. Defaults to None.
    """

    # Outlook SMTP server settings
    smtp_server = "smtp.office365.com"
    smtp_port = 587

    # Create the email object
    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    # Attach the body text (always required as fallback)
    msg.attach(MIMEText(body_text, 'plain'))

    # Attach the HTML body if provided
    if body_html:
        msg.attach(MIMEText(body_html, 'html'))

    try:
        # Connect to the server
        print(f"Connecting to {smtp_server}...")
        server = smtplib.SMTP(smtp_server, smtp_port)

        # Secure the connection
        server.starttls()

        # Login
        print("Logging in...")
        server.login(sender_email, sender_password)

        # Send the email
        print(f"Sending email to {recipient_email}...")
        server.send_message(msg)

        # Disconnect
        server.quit()
        print("Email sent successfully!")
        return True

    except smtplib.SMTPAuthenticationError:
        print("\nERROR: Authentication failed.")
        print("If you have 2FA enabled, you MUST use an 'App Password'.")
        print("Check your Microsoft Account -> Security -> Advanced Security Options.")
        return False
    except Exception as e:
        print(f"\nERROR: An error occurred: {e}")
        return False



# Ensure the script only runs the monitor function when executed directly
if __name__ == "__main__":
    # Check if the monitoring directory exists
    if not os.path.isdir(MONITOR_DIR):
        print(f"Error: The directory {MONITOR_DIR} does not exist or is inaccessible.")
        exit(1)

    try:
        monitor_directory()
    except KeyboardInterrupt:
        print("\nMonitor stopped by user (Ctrl+C). Exiting.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
