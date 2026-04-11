# SoundCloud Likes → Excel → Spotify Pipeline (WIP)

## Overview

## What Changed

1. Extract SoundCloud likes  
2. Export them to Excel  
3. Match tracks on Spotify  
4. Create a Spotify playlist  
5. Update Excel with Spotify match status  

## Project Structure

```text
soundcloud-parser/
|-- sc_likes_to_xlsx.py
|-- client.py
|-- exporter.py
|-- models.py
|-- parser.py
|-- parser_settings.example.json
|-- service.py
|-- settings.py
`-- .env
```

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Environment variables

Create a `.env` file with your SoundCloud credentials:

```bash
SOUNDCLOUD_CLIENT_ID=your_client_id
SOUNDCLOUD_USER_ID=your_user_id
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

## Usage

```bash
python sc_likes_to_xlsx.py
```

## Output

Running the script generates:

- `soundcloud_likes.xlsx`
- `soundcloud_livesets.xlsx`

Each row includes:

- Artist
- Song
- Artist Source
- Original Title
- Date Uploaded
- Date Liked
- SoundCloud URL

## Design Notes

- `SoundCloudClient` handles API pagination and retry behavior
- `SoundCloudTitleParser` owns title cleanup, parsing, and liveset classification
- `ExcelExporter` writes formatted Excel output
- `LikesExportService` coordinates the workflow

This keeps the code easier to test, extend, and eventually grow into the Spotify pipeline you described, without adding extra directory depth.
