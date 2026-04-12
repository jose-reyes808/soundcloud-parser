# SoundCloud Parser

This project is evolving from a local script into a backend-first web app that imports SoundCloud likes, matches them on Spotify, and creates a Spotify playlist for the user through Spotify OAuth.

## Current Direction

The repo now supports two modes:

- legacy local scripts for direct command-line use
- a new FastAPI web app scaffold that removes Excel from the user flow

The web app is the path forward.

## Project Structure

```text
soundcloud-parser/
|-- soundcloud_export_likes.py
|-- spotify_match_from_excel.py
|-- webapp.py
|-- parser_settings.example.json
|-- .env.example
|-- templates/
|   |-- import_not_found.html
|   |-- import_status.html
|   `-- index.html
`-- src/
    |-- __init__.py
    |-- config.py
    |-- models.py
    |-- soundcloud/
    |   |-- __init__.py
    |   |-- client.py
    |   |-- exporter.py
    |   |-- parser.py
    |   `-- service.py
    |-- spotify/
    |   |-- __init__.py
    |   |-- client.py
    |   |-- matcher.py
    |   `-- service.py
    `-- webapp/
        |-- __init__.py
        |-- app.py
        |-- import_runner.py
        |-- spotify_api.py
        |-- spotify_oauth.py
        `-- storage.py
```

## Web App Flow

1. User opens the home page
2. User enters:
   - SoundCloud user ID
   - SoundCloud client ID
   - desired Spotify playlist name
3. App redirects the user to Spotify OAuth
4. Spotify redirects back to the app callback
5. Backend creates an import job
6. Background processing fetches SoundCloud likes directly, matches them on Spotify, and creates a playlist
7. User watches progress on a status page

No Excel file is needed for the web flow.

## Installation

```bash
pip install -r requirements.txt
```

## Environment Variables

Start from `.env.example`.

```env
SOUNDCLOUD_CLIENT_ID=your_soundcloud_client_id
SOUNDCLOUD_USER_ID=your_soundcloud_user_id
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
WEBAPP_SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/auth/spotify/callback
WEBAPP_SESSION_SECRET=replace_with_a_long_random_secret
APP_BASE_URL=http://127.0.0.1:8000
```

Notes:

- `SPOTIFY_REDIRECT_URI` is still used by the older CLI script flow
- `WEBAPP_SPOTIFY_REDIRECT_URI` is used by the FastAPI web app
- in the Spotify Developer Dashboard, add the web app callback URI exactly as:

```text
http://127.0.0.1:8000/auth/spotify/callback
```

## Running the Web App

```bash
python webapp.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Current MVP Backend Features

- FastAPI app with session support
- Spotify OAuth redirect and callback flow
- SQLite-backed import job store
- background import execution
- SoundCloud likes fetch directly from API
- Spotify matching and playlist creation
- import status page with auto-refresh

## Legacy CLI Scripts

These still exist while the web app is being built out:

```bash
python soundcloud_export_likes.py
python spotify_match_from_excel.py --start-from-bottom --create-playlist --playlist-name "SoundCloud Likes"
```

## Next Good Backend Steps

- replace the in-process background task with a real job queue
- store matched/unmatched track rows in the database
- let users paste a SoundCloud profile URL instead of only a user ID
- add app-level auth if you want saved import history per user
