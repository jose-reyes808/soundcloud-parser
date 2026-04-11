from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from models import ExportResult, TrackRecord
from parser import SoundCloudTitleParser


class ExcelExporter:
    def __init__(self, title_parser: SoundCloudTitleParser) -> None:
        self.title_parser = title_parser

    def export(
        self,
        likes: list[TrackRecord],
        tracks_file: Path,
        livesets_file: Path,
    ) -> ExportResult:
        rows = [record.to_row() for record in likes]
        dataframe = pd.DataFrame(rows)

        if dataframe.empty:
            dataframe = pd.DataFrame(
                columns=[
                    "Artist",
                    "Song",
                    "Artist Source",
                    "Original Title",
                    "Date Uploaded",
                    "Date Liked",
                    "SoundCloud URL",
                ]
            )

        self._normalize_datetime_columns(dataframe)

        dataframe["Is_Liveset"] = dataframe.apply(
            lambda row: self.title_parser.is_liveset(
                row["Song"],
                row["Artist"],
                row["Original Title"],
            ),
            axis=1,
        )

        livesets_dataframe = dataframe[dataframe["Is_Liveset"]].drop(columns=["Is_Liveset"])
        tracks_dataframe = dataframe[~dataframe["Is_Liveset"]].drop(columns=["Is_Liveset"])

        tracks_dataframe.to_excel(tracks_file, index=False)
        livesets_dataframe.to_excel(livesets_file, index=False)

        self._autosize_excel_columns(tracks_file)
        self._autosize_excel_columns(livesets_file)

        artist_source_breakdown = {
            str(key): int(value)
            for key, value in dataframe["Artist Source"].value_counts().to_dict().items()
        }

        return ExportResult(
            total_likes=len(likes),
            track_count=len(tracks_dataframe),
            liveset_count=len(livesets_dataframe),
            artist_source_breakdown=artist_source_breakdown,
        )

    @staticmethod
    def _normalize_datetime_columns(dataframe: pd.DataFrame) -> None:
        for column_name in ["Date Uploaded", "Date Liked"]:
            if column_name in dataframe.columns:
                dataframe[column_name] = pd.to_datetime(
                    dataframe[column_name],
                    errors="coerce",
                ).dt.tz_localize(None)

    @staticmethod
    def _autosize_excel_columns(file_path: Path) -> None:
        workbook = load_workbook(file_path)
        worksheet = workbook.active

        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter

            for cell in column:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))

            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 100)

        workbook.save(file_path)
