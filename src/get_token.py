from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json", SCOPES
)
creds = flow.run_local_server(
    port=8082,
    access_type='offline',
    prompt='consent'
)
creds = flow.run_local_server(port=0)

print("ACCESS TOKEN:", creds.token)
print("REFRESH TOKEN:", creds.refresh_token)