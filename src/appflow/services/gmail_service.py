from googleapiclient.discovery import build

class GmailService:
    def __init__(self, credentials):
        self.service = build('gmail', 'v1', credentials=credentials)

    def search_emails(self, query: str):
        result = self.service.users().messages().list(
            userId='me',
            q=query,
            maxResults=20
        ).execute()

        return result.get('messages', [])

    def get_email(self, msg_id: str):
        message = self.service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()

        return message