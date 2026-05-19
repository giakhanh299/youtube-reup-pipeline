# YouTube Data API Upload Setup

This project uploads through YouTube Data API v3. Selenium remains optional and
is not used for the upload flow.

## Google Cloud Setup

1. Create or select a Google Cloud project.
2. Enable **YouTube Data API v3**.
3. Configure the OAuth consent screen.
4. Create an OAuth client ID for a desktop app.
5. Download the OAuth client JSON file.

## Local Config

Set these values in `configs/settings.json` or `.env`:

```text
YT_YOUTUBE_OAUTH_CREDENTIALS_JSON=E:/path/to/oauth_client.json
YT_YOUTUBE_OAUTH_TOKEN_JSON=runtime/state/youtube/token.json
```

Legacy `.env` files using this value are also supported:

```text
YT_YOUTUBE_TOKEN_PICKLE_PATH=./secrets/youtube_token.pickle
```

`youtube_oauth_token_json` is created after the first successful OAuth flow and
should be kept out of git.

## Queue Metadata

`VIDEO_QUEUE` can provide upload metadata:

```text
title,description,tags,categoryId,privacyStatus
```

`privacyStatus` defaults to `private` when omitted. `categoryId` defaults to
`22`.

## Sheet-Controlled Upload

Phase 6 reads pending uploads from the sheet tab configured by
`upload_sheet_name`, defaulting to:

```text
Video đã edit
```

Required columns:

```text
video_path,title,description,tags,categoryId,privacyStatus,upload_status,youtube_video_id,upload_error,upload_time
```

Run the isolated uploader:

```text
python scripts/upload_from_sheet.py
```

Rows with blank `upload_status` or `pending` are uploaded. The script writes
`uploading`, then `uploaded` plus the YouTube video ID and upload timestamp. On
failure it writes `failed` and a readable error message.

## Tests

Tests use mocked clients only. They must not run real YouTube uploads or require
real OAuth credentials.
