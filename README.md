# SoundCloud Parser

SoundCloud Parser is now a backend-first web app that takes a SoundCloud profile URL, sends the user through Spotify OAuth, imports their SoundCloud likes, matches tracks on Spotify, and creates a Spotify playlist for them.

The current public deployment is running on Render at `https://soundcloud-parser.onrender.com`.

For a deeper walkthrough of how the app is structured internally, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Current Status

The web app is the primary product now. The old one-off CLI entry scripts have been removed from the repo root so the codebase reflects the deployed experience more accurately.

What currently works:

- SoundCloud profile URL input on the landing page
- backend resolution of the SoundCloud profile to a user ID
- Spotify OAuth login and consent flow
- background import jobs through Redis + RQ
- SoundCloud likes fetching and Spotify matching
- private Spotify playlist creation
- live status page with:
  - current phase
  - processed likes out of total likes
  - matched and unmatched counts
  - current track being processed
- improved Tailwind-based UI for the landing page and status page

## Product Flow

1. User opens the site.
2. User pastes a SoundCloud profile URL and chooses a playlist name.
3. The backend resolves that profile into a SoundCloud user ID.
4. The user is redirected to Spotify and approves access.
5. The callback creates an import job in Postgres.
6. A background worker pulls the job from Redis.
7. The worker fetches SoundCloud likes, matches tracks on Spotify, and creates the playlist.
8. The status page polls the backend and shows live progress until the playlist is ready.

No Excel export is required for the web flow.

## Project Structure

```text
soundcloud-parser/
|-- webapp.py
|-- worker.py
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
        |-- queue.py
        |-- spotify_api.py
        |-- spotify_oauth.py
        |-- storage.py
        `-- tasks.py
```

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the web app:

```bash
python webapp.py
```

Run the worker in a second terminal:

```bash
python worker.py
```

Then open:

```text
http://127.0.0.1:8000
```

For local development, the app defaults to SQLite and a local Redis URL unless you override them in `.env`.

## Environment Variables

Start from `.env.example`.

```env
SOUNDCLOUD_CLIENT_ID=your_soundcloud_client_id
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
WEBAPP_SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/auth/spotify/callback
WEBAPP_SESSION_SECRET=replace_with_a_long_random_secret
APP_BASE_URL=http://127.0.0.1:8000
APP_ENV=development
DATABASE_URL=sqlite:///webapp.sqlite3
REDIS_URL=redis://localhost:6379/0
```

Notes:

- `SOUNDCLOUD_CLIENT_ID` stays entirely server-side and is never entered by the user
- `WEBAPP_SPOTIFY_REDIRECT_URI` must exactly match the callback configured in the Spotify Developer Dashboard
- in production, `DATABASE_URL` should point to Render Postgres and `REDIS_URL` should point to Render Key Value

## Render Deployment

The current deployment was brought up by creating the services directly in Render.

### Render Services

- Web service: `soundcloud-parser`
- Background worker: `soundcloud-parser-worker`
- Postgres database: `soundcloud-parser-db`
- Key Value / Redis: `soundcloud-parser-redis`

### Manual Render Setup

1. Push the repo to GitHub.
2. Create a Render account and connect the repo.
3. Create a **Web Service** named `soundcloud-parser`.
4. Use:
   - build command: `pip install -r requirements.txt`
   - start command: `uvicorn webapp:app --host 0.0.0.0 --port $PORT`
5. Create a **Postgres** instance named `soundcloud-parser-db`.
6. Copy its internal connection string into `DATABASE_URL`.
7. Create a **Key Value** instance named `soundcloud-parser-redis`.
8. Copy its internal connection string into `REDIS_URL`.
9. Create a **Background Worker** named `soundcloud-parser-worker`.
10. Use:
    - build command: `pip install -r requirements.txt`
    - start command: `python worker.py`
11. Add the same app environment variables to both the web service and the worker.
12. Set:
    - `APP_ENV=production`
    - `APP_BASE_URL=https://soundcloud-parser.onrender.com`
    - `WEBAPP_SPOTIFY_REDIRECT_URI=https://soundcloud-parser.onrender.com/auth/spotify/callback`
13. In the Spotify Developer Dashboard, add that exact callback URL.

### Required Render Environment Variables

- `APP_ENV=production`
- `APP_BASE_URL=https://soundcloud-parser.onrender.com`
- `WEBAPP_SESSION_SECRET=<long random secret>`
- `SOUNDCLOUD_CLIENT_ID=<server-side soundcloud client id>`
- `SPOTIFY_CLIENT_ID=<spotify app client id>`
- `SPOTIFY_CLIENT_SECRET=<spotify app client secret>`
- `WEBAPP_SPOTIFY_REDIRECT_URI=https://soundcloud-parser.onrender.com/auth/spotify/callback`
- `DATABASE_URL=<internal postgres url>`
- `REDIS_URL=<internal key value url>`

## UI and Progress Tracking

The current UI is server-rendered with Tailwind CSS loaded via CDN. That keeps the stack simple while still making the app feel much more polished than the original templates.

The status page now polls `/api/imports/{job_id}` and displays:

- current job state
- current processing phase
- total likes discovered
- processed likes so far
- matched count
- unmatched count
- the current artist and song being processed
- the final playlist link when the job completes
