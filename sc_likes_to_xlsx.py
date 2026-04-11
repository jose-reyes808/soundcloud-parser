from __future__ import annotations

from pathlib import Path

from service import LikesExportService
from settings import SettingsLoader


def main() -> None:
    project_root = Path(__file__).resolve().parent
    settings_loader = SettingsLoader(project_root)

    app_config = settings_loader.load_app_config()
    parser_settings = settings_loader.load_parser_settings()

    service = LikesExportService(
        app_config=app_config,
        parser_settings=parser_settings,
    )
    service.run()


if __name__ == "__main__":
    main()
