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

`youtube_oauth_token_json` is created after the first successful OAuth flow and
should be kept out of git.

## Queue Metadata

`VIDEO_QUEUE` can provide upload metadata:

```text
title,description,tags,categoryId,privacyStatus
```

`privacyStatus` defaults to `private` when omitted. `categoryId` defaults to
`22`.

## Tests

Tests use mocked clients only. They must not run real YouTube uploads or require
real OAuth credentials.
