import base64
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
DOWNLOAD_DIR = BASE_DIR / "downloads"

TARGET_SENDER = "youssefkrichen6@gmail.com"

from app.extraction.email_download_agent import EmailDownloadExtractionAgent


def get_gmail_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError("credentials.json introuvable.")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE),
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def get_header(headers: List[Dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def find_attachments(parts: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not parts:
        return []

    attachments = []

    for part in parts:
        filename = part.get("filename")
        body = part.get("body", {})
        mime_type = part.get("mimeType")

        if filename and body.get("attachmentId"):
            attachments.append({
                "filename": filename,
                "mime_type": mime_type,
                "attachment_id": body["attachmentId"]
            })

        if part.get("parts"):
            attachments.extend(find_attachments(part["parts"]))

    return attachments


def safe_filename(filename: str) -> str:
    return filename.replace("/", "_").replace("\\", "_")


def download_attachment(gmail, message_id: str, attachment_id: str, filename: str):
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    attachment = gmail.users().messages().attachments().get(
        userId="me",
        messageId=message_id,
        id=attachment_id
    ).execute()

    data = attachment.get("data")

    if not data:
        return None

    file_data = base64.urlsafe_b64decode(data.encode("utf-8"))

    file_path = DOWNLOAD_DIR / safe_filename(filename)

    file_path.write_bytes(file_data)

    return file_path


def main():
    gmail = get_gmail_service()
    extraction_agent = EmailDownloadExtractionAgent()

    query = f"from:{TARGET_SENDER} has:attachment newer_than:30d"

    result = gmail.users().messages().list(
        userId="me",
        q=query,
        maxResults=20
    ).execute()

    messages = result.get("messages", [])

    if not messages:
        print(f"Aucun email avec pièce jointe trouvé depuis {TARGET_SENDER}")
        return

    print(f"{len(messages)} email(s) trouvé(s) depuis {TARGET_SENDER}")

    for item in messages:
        message_id = item["id"]

        message = gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

        payload = message.get("payload", {})
        headers = payload.get("headers", [])

        subject = get_header(headers, "Subject")
        sender = get_header(headers, "From")
        date = get_header(headers, "Date")

        print("\n------------------------------")
        print("From    :", sender)
        print("Subject :", subject)
        print("Date    :", date)

        attachments = find_attachments(payload.get("parts"))

        if not attachments:
            print("Aucune pièce jointe dans cet email.")
            continue

        for att in attachments:
            saved_path = download_attachment(
                gmail=gmail,
                message_id=message_id,
                attachment_id=att["attachment_id"],
                filename=att["filename"]
            )

            if saved_path:
                print("Téléchargé :", saved_path)
                extraction_result = extraction_agent.extract_file(saved_path)
                print("Extraction :", json.dumps(extraction_result.__dict__, ensure_ascii=False))

        # Optionnel : marquer l'email comme lu après téléchargement
        gmail.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()


if __name__ == "__main__":
    main()
