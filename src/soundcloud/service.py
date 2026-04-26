from __future__ import annotations

"""Application service for the legacy SoundCloud likes export command."""

from src.models import AppConfig, ExportResult, ParserSettings
from src.soundcloud.client import SoundCloudClient
from src.soundcloud.exporter import ExcelExporter
from src.soundcloud.parser import SoundCloudTitleParser

# This service represents the old local export flow as one coherent use case.
# It exists mainly to keep the command surface thin and the orchestration readable.
class LikesExportService:
    """Coordinate fetching, parsing, and writing SoundCloud likes to disk."""

    def __init__(self, app_config: AppConfig, parser_settings: ParserSettings) -> None:
        """Compose the SoundCloud client, parser, and exporter for one run."""

        self.app_config = app_config
        self.parser_settings = parser_settings
        self.title_parser = SoundCloudTitleParser(parser_settings)
        self.client = SoundCloudClient(
            client_id=app_config.soundcloud_client_id,
            user_id=app_config.soundcloud_user_id,
            title_parser=self.title_parser,
        )
        self.exporter = ExcelExporter(self.title_parser)

    # The service prints a lightweight console summary because this flow is
    # primarily used interactively from the terminal.
    def run(self) -> ExportResult:
        """Execute the full export workflow and print a simple console summary."""

        likes = self.client.get_likes()
        print(f"Pages completed. Total likes collected: {len(likes)}")

        if not likes:
            print("No likes fetched. Empty workbooks will still be written.")

        result = self.exporter.export(
            likes=likes,
            tracks_file=self.app_config.tracks_output_file,
            livesets_file=self.app_config.livesets_output_file,
        )

        print("\nBreakdown:")
        print(f"Tracks: {result.track_count}")
        print(f"Live sets: {result.liveset_count}")

        print("\nArtist Source Breakdown:")
        for source, count in result.artist_source_breakdown.items():
            print(f"{source}: {count}")

        print("Done.")
        return result
