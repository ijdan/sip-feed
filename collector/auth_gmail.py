"""Lance ce script une seule fois pour générer gmail_token.json."""
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": input("Colle ton Google Client ID : ").strip(),
            "client_secret": input("Colle ton Google Client Secret : ").strip(),
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    SCOPES,
)

creds = flow.run_local_server(port=0)

with open("gmail_token.json", "w") as f:
    f.write(creds.to_json())

print("\ngmail_token.json créé avec succès.")
