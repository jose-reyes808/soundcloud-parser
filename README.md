# SoundCloud Parser

This project exports SoundCloud likes to Excel, matches those rows against Spotify tracks, and can create a Spotify playlist from the matched results.

## Project Structure

```text
soundcloud-parser/
|-- soundcloud_export_likes.py
|-- spotify_match_from_excel.py
|-- parser_settings.example.json
|-- .env.example
|-- src/
|   |-- __init__.py
|   |-- config.py
|   |-- models.py
|   |-- soundcloud/
|   |   |-- __init__.py
|   |   |-- client.py
|   |   |-- exporter.py
|   |   |-- parser.py
|   |   `-- service.py
|   `-- spotify/
|       |-- __init__.py
|       |-- client.py
|       |-- matcher.py
|       `-- service.py
`-- .env
```

## Pipeline

1. Export SoundCloud likes to Excel
2. Match the Excel rows to Spotify tracks
3. Optionally create a Spotify playlist from matched tracks

## Installation

```bash
git clone https://github.com/jose-reyes808/soundcloud-parser.git 
cd soundcloud-parser
pip install -r requirements.txt
```

## Configuration

### 1. Environment variables

Create a `.env` file with your SoundCloud and Spotify credentials. You can start from `.env.example`:

```env
SOUNDCLOUD_CLIENT_ID=your_client_id
SOUNDCLOUD_USER_ID=your_user_id
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

### 2. Parser settings

Copy the example settings file and create your own local version:

```bash
cp parser_settings.example.json parser_settings.json
```

PowerShell:

```powershell
Copy-Item parser_settings.example.json parser_settings.json
```

`parser_settings.json` is ignored by git so each user can customize their own values safely.

You can update these lists there:

- `liveset_keywords`
- `cutoff_patterns`
- `remove_patterns`
- `paren_keywords`

## Spotify App Setup

To use Spotify matching or playlist creation, create a Spotify app in the Spotify Developer Dashboard:

1. Go to `https://developer.spotify.com/dashboard`
2. Create a new app
3. Open the app settings
4. Copy the `Client ID`
5. Reveal and copy the `Client Secret`
6. Add this Redirect URI:

```text
http://127.0.0.1:8888/callback
```

The redirect URI in the dashboard must exactly match the value in your `.env`.

## Usage

### SoundCloud export

```bash
python soundcloud_export_likes.py
```

### Spotify matching

Process the full file:

```bash
python spotify_match_from_excel.py
```

Process the full file starting from the bottom of the sheet:

```bash
python spotify_match_from_excel.py --start-from-bottom
```

Use a different Excel input file:

```bash
python spotify_match_from_excel.py --input-file your_file.xlsx
```

Create a private playlist from matched rows:

```bash
python spotify_match_from_excel.py --create-playlist --playlist-name "SoundCloud Imports"
```

Create a playlist from all rows in bottom-to-top order:

```bash
python spotify_match_from_excel.py --start-from-bottom --create-playlist --playlist-name "SoundCloud Likes"
```

## First Spotify Run

On the first Spotify run, the script will:

1. Print an authorization URL
2. Open it in your browser when possible
3. Ask you to approve access
4. Redirect your browser to `http://127.0.0.1:8888/callback`
5. Ask you to paste that full redirected URL back into the terminal

The script stores refreshable tokens in `spotify_tokens.json` for future runs.
