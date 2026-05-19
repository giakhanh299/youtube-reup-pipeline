from pathlib import Path
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

BASE_DIR = Path(__file__).resolve().parents[1]
SECRETS_DIR = BASE_DIR / "secrets"

CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"
TOKEN_PICKLE_FILE = SECRETS_DIR / "youtube_token.pickle"


def main():
    SECRETS_DIR.mkdir(exist_ok=True)

    credentials = None

    if TOKEN_PICKLE_FILE.exists():
        with open(TOKEN_PICKLE_FILE, "rb") as token:
            credentials = pickle.load(token)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        if not CLIENT_SECRET_FILE.exists():
            raise FileNotFoundError(
                f"Không tìm thấy {CLIENT_SECRET_FILE}. "
                "Hãy tải OAuth Client JSON từ Google Cloud và đổi tên thành client_secret.json"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_FILE),
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
        )

        with open(TOKEN_PICKLE_FILE, "wb") as token:
            pickle.dump(credentials, token)

    print(f"OK: Đã tạo token tại {TOKEN_PICKLE_FILE}")


if __name__ == "__main__":
    main()