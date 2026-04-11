from __future__ import annotations

import re

from models import ParserSettings


class SoundCloudTitleParser:
    def __init__(self, settings: ParserSettings) -> None:
        self.settings = settings

    def clean_promotional(self, text: str | None) -> str | None:
        if not text:
            return text

        cleaned_text = text.strip()
        cleaned_text = re.sub(
            r"\([^)]*out now[^)]*\)",
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )

        for pattern in self.settings.cutoff_patterns:
            cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE)

        for pattern in self.settings.remove_patterns:
            cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE)

        cleaned_text = re.sub(r"#\d+\s*chart\b", "", cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r"\*.*?\*", "", cleaned_text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text)
        cleaned_text = re.sub(r"\s*-\s*$", "", cleaned_text)
        cleaned_text = re.sub(r"\(\s*\)", "", cleaned_text)
        cleaned_text = re.sub(r"\[\s*\]", "", cleaned_text)
        return cleaned_text.strip()

    def postprocess_text(self, text: str | None) -> str | None:
        if not text:
            return text

        processed_text = text.strip()
        processed_text = self.clean_promotional(processed_text)
        processed_text = re.sub(r"\(\s*\)", "", processed_text)
        processed_text = re.sub(r"\[\s*\]", "", processed_text)
        processed_text = re.sub(r"\(\s*$", "", processed_text)
        processed_text = re.sub(r"^\s*\)", "", processed_text)
        processed_text = re.sub(r"\[\s*$", "", processed_text)
        processed_text = re.sub(r"^\s*\]", "", processed_text)
        processed_text = re.sub(r"[-|:,;/]+\s*$", "", processed_text)
        processed_text = re.sub(r"\(\s+", "(", processed_text)
        processed_text = re.sub(r"\s+\)", ")", processed_text)
        processed_text = re.sub(r"\[\s+", "[", processed_text)
        processed_text = re.sub(r"\s+\]", "]", processed_text)
        processed_text = re.sub(r"\s+", " ", processed_text)
        return processed_text.strip()

    def is_liveset(
        self,
        song: str,
        artist: str = "",
        original_title: str = "",
    ) -> bool:
        searchable_text = f"{artist} {song} {original_title}".lower()

        for keyword in self.settings.liveset_keywords:
            normalized_keyword = keyword.lower()
            if normalized_keyword == "xs":
                if re.search(r"(?:^|\s)xs(?:\s|$)", searchable_text):
                    return True
                continue

            if normalized_keyword in searchable_text:
                return True

        return False

    def parse_title(self, title: str | None, uploader: str) -> tuple[str, str, str]:
        if not title:
            return uploader, "", "Uploader Fallback"

        original_title = self.clean_promotional(title.strip()) or ""
        bracket_contents = re.findall(r"\[(.*?)\]", original_title)

        keep_brackets = []
        for content in bracket_contents:
            if re.search(r"remix|edit|flip|bootleg|rework|vip|mix", content, re.IGNORECASE):
                keep_brackets.append(f"[{content.strip()}]")

        title_without_brackets = re.sub(r"\[.*?\]", "", original_title)
        title_with_filtered_parens = re.sub(
            r"\((.*?)\)",
            self._filter_parenthetical_content,
            title_without_brackets,
        )

        normalized_title = re.sub(r"[–—]", "-", title_with_filtered_parens)
        normalized_title = re.sub(r"\s+", " ", normalized_title).strip()

        parts = re.split(r"\s+[-–—|]\s+", normalized_title, maxsplit=1)

        if len(parts) == 2:
            artist = parts[0].strip()
            song = parts[1].strip()
            source = "Parsed from Title"
        else:
            artist = uploader
            song = normalized_title.strip()
            source = "Uploader Fallback"

        if keep_brackets:
            song = f"{song} {' '.join(keep_brackets)}".strip()

        clean_artist = self.postprocess_text(artist) or ""
        clean_song = self.postprocess_text(song) or ""
        return clean_artist, clean_song, source

    def _filter_parenthetical_content(self, match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if any(keyword in content.lower() for keyword in self.settings.paren_keywords):
            return f"({content})"
        return ""
