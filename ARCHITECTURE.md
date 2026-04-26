## Architecture

This project started as a practical utility for moving a long history of SoundCloud likes into Spotify without doing the work by hand. The current version is a small backend-first web application that keeps the user flow simple while keeping the messy parts on the server side.

At a high level, the system does four things well:

1. Accept a SoundCloud profile URL from the user.
2. Send the user through Spotify OAuth.
3. Run the import in the background.
4. Stream job progress back to a status page.

## System Overview

The application is split into a few clear layers:

- `templates/`
  Server-rendered HTML for the landing page, status page, and simple error states.
- `src/webapp/`
  FastAPI routes, Spotify OAuth handling, job orchestration, queue integration, and persistence.
- `src/soundcloud/`
  SoundCloud profile resolution, likes retrieval, and title parsing logic.
- `src/spotify/`
  Spotify matching logic and the older CLI-oriented Spotify client code that the matching heuristics still build on conceptually.
- `src/models.py`
  Shared data models used across the repo.
- `src/config.py`
  Environment and parser-settings loading.

The deployed app runs as two processes:

- a web service that handles HTTP requests and OAuth callbacks
- a worker process that consumes import jobs from Redis

## Request Flow

The user-facing flow is intentionally short:

1. The user opens the landing page.
2. They paste a SoundCloud profile URL and choose a playlist name.
3. The web app resolves that profile to a numeric SoundCloud user ID.
4. The app redirects the user to Spotify OAuth.
5. Spotify redirects back to `/auth/spotify/callback`.
6. The callback stores a new import job in the database and enqueues background work.
7. The worker fetches likes from SoundCloud, parses titles, searches Spotify, and creates the playlist.
8. The status page polls `/api/imports/{job_id}` for progress until the run completes.

The important design choice here is that playlist creation does not happen inside the request-response cycle. That work is pushed into the worker so the site stays responsive and the job can take its time.

## Web Layer

The FastAPI app in [src/webapp/app.py] is intentionally thin.

Its responsibilities are:

- render the landing page
- validate incoming form data
- resolve the SoundCloud profile before starting OAuth
- complete Spotify OAuth
- create a persisted import job
- enqueue background work
- expose job state to the frontend

This keeps the route handlers focused on coordination rather than business logic.

## Background Processing

The worker entrypoint in [worker.py](c:/Users/Jose/Documents/py/soundcloud-parser/worker.py) listens on the Redis-backed `imports` queue.

When a job is dequeued, [src/webapp/tasks.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/webapp/tasks.py) bootstraps the dependencies and hands control to [src/webapp/import_runner.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/webapp/import_runner.py).

`WebImportRunner` is where the long-running workflow lives:

- mark the job as running
- fetch SoundCloud likes
- reverse the list if the user wants oldest-first ordering
- search Spotify for each parsed track
- record matched and unmatched counts as it goes
- create the Spotify playlist
- mark the job completed or failed

The status page works because progress is persisted after each meaningful step rather than only at the end.

## Persistence

The job store in [src/webapp/storage.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/webapp/storage.py) uses SQLAlchemy and is designed around one central record: `ImportJob`.

Each job stores:

- the SoundCloud user being imported
- playlist settings
- Spotify token state
- coarse-grained status such as `pending`, `running`, `completed`, or `failed`
- fine-grained progress such as:
  - current phase
  - total tracks
  - processed tracks
  - current artist and song
  - matched and unmatched counts

That model is intentionally simple, but it is enough to support reliable progress updates and post-run debugging.

## SoundCloud Integration

The SoundCloud side is split in two:

- [src/soundcloud/client.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/soundcloud/client.py)
  Talks to SoundCloud endpoints, resolves profile URLs, and paginates through likes.
- [src/soundcloud/parser.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/soundcloud/parser.py)
  Cleans messy titles into something useful for matching.

That parser matters more than it might seem at first glance. SoundCloud titles often include promotional text, remixes, uploader-specific formatting, and liveset naming conventions. Cleaning that input before it hits Spotify search is what makes the playlist quality acceptable.

## Spotify Integration

Spotify is handled through two different code paths:

- [src/webapp/spotify_oauth.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/webapp/spotify_oauth.py)
  Owns the Authorization Code flow for the web app.
- [src/webapp/spotify_api.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/webapp/spotify_api.py)
  Uses stored tokens to search tracks and create playlists.

Track selection is driven by [src/spotify/matcher.py](c:/Users/Jose/Documents/py/soundcloud-parser/src/spotify/matcher.py), which scores candidates based on artist and song similarity rather than trusting the first search result.

That is a small but important product decision: users care more about getting the right track than about squeezing a few milliseconds out of search.

## Deployment

The production deployment is built for Render:

- web service for FastAPI
- background worker for RQ
- Postgres for job persistence
- Key Value / Redis for queueing

The current public deployment was brought up manually in Render so each piece of infrastructure could be verified in isolation.

## Design Notes

There are a few guiding principles behind the current architecture:

- Keep secrets server-side.
  Users never need to enter Spotify app credentials or the SoundCloud client ID.
- Push slow work off the request thread.
  Imports can take a while, so the queue/worker split is worth it.
- Prefer explicit progress over opaque background work.
  A visible job state is much easier to trust and debug.
- Keep the frontend simple until the product shape stabilizes.
  Server-rendered pages plus a polling endpoint are enough for this stage.

## Where This Can Grow

If the project keeps evolving, the strongest next architectural extensions would be:

- storing per-track results for auditability and retries
- adding user accounts and import history
- introducing a richer frontend once the backend shape settles
- formal schema migrations instead of lightweight runtime column patching

For now, the current structure is intentionally modest: small enough to reason about, but organized enough to keep growing without turning back into a script pile.
