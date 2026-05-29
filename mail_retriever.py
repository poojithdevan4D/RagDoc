import os
import mailbox
import shutil
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

def locate_thunderbird_inbox():
    # Standard location on Windows
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    
    profiles_dir = os.path.join(appdata, "Thunderbird", "Profiles")
    if not os.path.isdir(profiles_dir):
        return None
        
    # Find any imap.gmail.com/INBOX file recursively
    for root, dirs, files in os.walk(profiles_dir):
        if "INBOX" in files:
            if "ImapMail" in root:
                return os.path.join(root, "INBOX")
                
    # Fallback to any file named INBOX (without extension)
    for root, dirs, files in os.walk(profiles_dir):
        if "INBOX" in files and not root.endswith(".sbd"):
            return os.path.join(root, "INBOX")
            
    return None

def fetch_attachments_from_inbox(inbox_path, output_dir="incoming_reports"):
    if not inbox_path or not os.path.exists(inbox_path):
        print(f"Error: Inbox path {inbox_path} not found.")
        return []
        
    # Clear the staging folder first to prevent mixing with old runs
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            fp = os.path.join(output_dir, f)
            if os.path.isfile(fp):
                os.unlink(fp)
    else:
        os.makedirs(output_dir)
        
    mbox = mailbox.mbox(inbox_path)
    messages_with_dates = []
    
    # Pre-parse messages and gather dates for sorting
    for idx, msg in enumerate(mbox):
        try:
            email_msg = BytesParser(policy=policy.default).parsebytes(msg.as_bytes())
            date_str = email_msg["date"]
            msg_date = None
            if date_str:
                try:
                    msg_date = parsedate_to_datetime(date_str)
                except Exception:
                    pass
            messages_with_dates.append((msg_date, email_msg, idx))
        except Exception as e:
            print(f"Error parsing date of message {idx}: {e}")
            
    # Sort messages by date (newest first). Keep messages without dates at the end.
    messages_with_dates.sort(key=lambda x: x[0] or parsedate_to_datetime("Mon, 1 Jan 1990 00:00:00 +0000"), reverse=True)
    
    extracted_files = []
    seen_months = set() # Track months we have already saved to avoid duplicates
    
    print(f"Scanning {len(messages_with_dates)} offline messages sorted by date...")
    for msg_date, email_msg, idx in messages_with_dates:
        try:
            subject = email_msg["subject"] or "(No Subject)"
            
            # Check all parts of email for attachments
            for part in email_msg.walk():
                filename = part.get_filename()
                if filename:
                    lower_fn = filename.lower()
                    
                    # Target monthly reports in docx or pdf
                    if "monthly" in lower_fn or lower_fn.endswith(".docx") or lower_fn.endswith(".pdf"):
                        # Differentiate months from the file name to only get the latest version of each month
                        # e.g., 'Monthly_Progress_Report_Jan_v2.pdf' -> month key 'jan'
                        month_key = None
                        for m in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]:
                            if m in lower_fn:
                                month_key = m
                                break
                                
                        # If a specific month is identified and we already saved a newer report for it, skip this one
                        if month_key:
                            if month_key in seen_months:
                                print(f"Skipping older report '{filename}' for month '{month_key.upper()}'")
                                continue
                            seen_months.add(month_key)
                            
                        filepath = os.path.join(output_dir, filename)
                        payload = part.get_payload(decode=True)
                        if payload:
                            with open(filepath, "wb") as f:
                                f.write(payload)
                            formatted_date = msg_date.strftime("%Y-%m-%d %H:%M") if msg_date else "Unknown Date"
                            print(f"Extracted latest report '{filename}' (Email Date: {formatted_date})")
                            extracted_files.append(filepath)
                            
                            # If we have collected 3 distinct months for the quarter, we can optimize and stop
                            if len(seen_months) >= 3:
                                print("Successfully collected 3 distinct monthly reports for the quarter. Stopping search.")
                                return extracted_files
        except Exception as e:
            print(f"Error parsing message attachment {idx}: {e}")
            
    return extracted_files
