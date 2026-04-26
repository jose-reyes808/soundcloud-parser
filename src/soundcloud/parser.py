from __future__ import annotations

"""Title-cleaning and parsing rules for noisy SoundCloud track names."""

import re

from src.models import ParserSettings


# SoundCloud metadata is noisy enough that title interpretation deserves its
# own domain object. Treating parsing as a separate concern keeps the import
# pipeline readable and makes the matching behavior easier to refine over time.
class SoundCloudTitleParser:
    """Convert raw SoundCloud titles into cleaner artist and song values."""

    VERSION_ONLY_PATTERN = re.compile(
        r"^(?:[a-z0-9&'.,+\s]+)\b(?:remix|edit|flip|bootleg|rework|vip|mix)\b$",
        re.IGNORECASE,
    )
    ARTIST_HINT_PATTERN = re.compile(
        r"\b(?:feat|ft|featuring|vs|x|with|and)\b|[&,]",
        re.IGNORECASE,
    )
    STRICT_TITLE_SEPARATOR_PATTERN = re.compile(r"\s+[-–—|]\s+")
    LOOSE_TITLE_SEPARATOR_PATTERN = re.compile(r"\s*[-–—|]\s+")

    def __init__(self, settings: ParserSettings) -> None:
        """Store the parser rules that drive cleanup and liveset detection."""

        self.settings = settings

    # The parser removes marketing language aggressively because Spotify search
    # quality depends far more on canonical track text than on release copy.
    def clean_promotional(self, text: str | None) -> str | None:
        """Strip common release-marketing text from a track title."""

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

    # This second pass is about normalization, not interpretation. By the time
    # we reach it, the goal is to make strings stable for display and matching.
    def postprocess_text(self, text: str | None) -> str | None:
        """Normalize punctuation and whitespace after the main cleanup passes."""

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

    # Livesets are treated as a different output category because they tend to
    # behave poorly in track-by-track matching workflows and exports.
    def is_liveset(
        self,
        song: str,
        artist: str = "",
        original_title: str = "",
    ) -> bool:
        """Decide whether a parsed row looks like a liveset instead of a track."""

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

    # The parser optimizes for recovering a useful search key, not for perfect
    # bibliographic accuracy. When the title is weak, falling back to uploader
    # data is often better than pretending the record is unusable.
    def parse_title(self, title: str | None, uploader: str) -> tuple[str, str, str]:
        """Extract artist and song names from a raw SoundCloud title.

        The parser prefers `Artist - Song` style titles. If that signal is not
        present, it falls back to the uploader name as the artist so downstream
        matching still has a reasonable query to work with.
        """

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

        parts = self.STRICT_TITLE_SEPARATOR_PATTERN.split(normalized_title, maxsplit=1)
        if len(parts) != 2:
            parts = self.LOOSE_TITLE_SEPARATOR_PATTERN.split(normalized_title, maxsplit=1)

        if len(parts) == 2:
            left_part = parts[0].strip()
            right_part = parts[1].strip()

            # A split title is not always an artist/title split. Tracks like
            # "Melbournia - Will Sparks Edit" use the suffix as version
            # metadata rather than as a standalone title. In that shape, the
            # uploader is often a better artist signal than the left-hand side,
            # and preserving the full title gives the matcher more context.
            if self._looks_like_version_only_fragment(right_part):
                artist = uploader
                song = normalized_title.strip()
                source = "Uploader Fallback"
            elif self._looks_like_reversed_artist_credit(left_part, right_part):
                artist = right_part
                song = left_part
                source = "Parsed from Reversed Title"
            else:
                artist = left_part
                song = right_part
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

    # Parenthetical content is preserved only when it changes identity rather
    # than presentation; remix labels matter, generic release copy does not.
    def _filter_parenthetical_content(self, match: re.Match[str]) -> str:
        """Keep only parenthetical text that looks musically meaningful."""

        content = match.group(1).strip()
        if any(keyword in content.lower() for keyword in self.settings.paren_keywords):
            return f"({content})"
        return ""

    @classmethod
    def _looks_like_version_only_fragment(cls, value: str) -> bool:
        """Detect suffixes that are version labels rather than song titles.

        This heuristic is intentionally narrow. We only fall back when the
        right-hand fragment looks like a bare edit/remix credit on its own,
        which helps with mislabeled uploads without weakening the normal
        `Artist - Song` parsing path.
        """

        normalized_value = value.strip()
        if not normalized_value:
            return False
        if "(" in normalized_value or "[" in normalized_value:
            return False
        return bool(cls.VERSION_ONLY_PATTERN.fullmatch(normalized_value))

    @classmethod
    def _looks_like_reversed_artist_credit(cls, left_part: str, right_part: str) -> bool:
        """Detect malformed `Song - Artist` titles before uploader fallback.

        Some repost channels publish tracks as `Song- Artist feat.Guest` instead
        of `Artist - Song`. We only reverse the split when the right-hand side
        looks strongly like an artist credit and the left-hand side does not.
        """

        normalized_left = left_part.strip()
        normalized_right = right_part.strip()
        if not normalized_left or not normalized_right:
            return False
        if cls._looks_like_artist_credit(normalized_left):
            return False
        return cls._looks_like_artist_credit(normalized_right)

    @classmethod
    def _looks_like_artist_credit(cls, value: str) -> bool:
        """Decide whether a fragment resembles a contributor credit string."""

        normalized_value = value.strip()
        if not normalized_value:
            return False
        if cls.ARTIST_HINT_PATTERN.search(normalized_value):
            return True

        words = [word for word in re.split(r"\s+", normalized_value) if word]
        if len(words) <= 4:
            capitalized_words = sum(1 for word in words if word[:1].isupper())
            if capitalized_words == len(words):
                return True

        return False
