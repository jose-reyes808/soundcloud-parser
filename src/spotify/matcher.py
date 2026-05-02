from __future__ import annotations

"""Heuristics for selecting the most likely Spotify track match."""

import re
from difflib import SequenceMatcher
from typing import Any

from src.models import SpotifyTrackMatch

# The matcher is intentionally decoupled from API access. Search quality tends
# to evolve independently of transport concerns, and this keeps that iteration
# loop local to one place.
class SpotifyTrackMatcher:
    """Score Spotify search results against a parsed artist and song pair."""

    MINIMUM_MATCH_SCORE = 0.55

    FEATURE_PATTERN = re.compile(r"\b(?:feat|ft|featuring)\.?\b", re.IGNORECASE)
    FEATURE_BLOCK_PATTERN = re.compile(
        r"[\(\[]\s*(?:feat|ft|featuring)\.?\s+[^\)\]]+[\)\]]",
        re.IGNORECASE,
    )
    TRAILING_COLLABORATOR_TITLE_PATTERN = re.compile(
        r"\s+\b(?:with|w/)\b\s+.+$",
        re.IGNORECASE,
    )
    TITLE_DECORATION_PATTERN = re.compile(
        r"\b(?:teaser|preview|forthcoming|official|album version|radio edit|radio mix)\b",
        re.IGNORECASE,
    )
    TITLE_SUFFIX_SEPARATOR_PATTERN = re.compile(r"\s+-\s+")
    MIX_DESCRIPTOR_PATTERN = re.compile(
        r"[\(\[]\s*([^\)\]]*\b(?:original mix|extended mix|club mix|mix|edit|remix|vip|bootleg|rework)\b[^\)\]]*)\s*[\)\]]",
        re.IGNORECASE,
    )
    ARTIST_SPLIT_PATTERN = re.compile(
        r"\s*(?:,|&|\band\b|\bvs\b|/|;|\bwith\b|\bx\b|\bfeat\b\.?|\bft\b\.?|\bfeaturing\b)\s*",
        re.IGNORECASE,
    )

    # The system is biased toward false negatives over false positives here.
    # It is better to leave a track unmatched than to quietly add the wrong song
    # to a user's playlist and erode trust in the import.
    def match(
        self,
        artist: str,
        song: str,
        candidates: list[dict[str, Any]],
        search_query: str,
    ) -> SpotifyTrackMatch | None:
        """Return the strongest candidate above the minimum confidence threshold."""

        best_match = self.find_best_candidate(artist, song, candidates, search_query)
        if best_match is None or best_match.match_score < self.MINIMUM_MATCH_SCORE:
            return None
        return best_match

    def find_best_candidate(
        self,
        artist: str,
        song: str,
        candidates: list[dict[str, Any]],
        search_query: str,
    ) -> SpotifyTrackMatch | None:
        """Return the strongest Spotify candidate even if it is below threshold.

        Review tooling benefits from seeing the best near-miss for unmatched
        rows. The acceptance threshold remains a separate policy decision so we
        can expose debugging data without silently broadening what gets added to
        playlists.
        """

        best_match: SpotifyTrackMatch | None = None

        for candidate in candidates:
            score = self._score_candidate(artist, song, candidate)
            if best_match is not None and score <= best_match.match_score:
                continue

            candidate_artists = ", ".join(
                artist_item.get("name", "")
                for artist_item in candidate.get("artists", [])
                if artist_item.get("name")
            )

            best_match = SpotifyTrackMatch(
                spotify_track_id=str(candidate.get("id", "")),
                spotify_uri=str(candidate.get("uri", "")),
                matched_artist=candidate_artists,
                matched_song=str(candidate.get("name", "")),
                match_score=round(score, 4),
                search_query=search_query,
                album_name=self._optional_string(candidate.get("album", {}).get("name")),
                external_url=self._optional_string(
                    candidate.get("external_urls", {}).get("spotify")
                ),
            )

        return best_match

    # When both artist and song are available, we spend that structure in the
    # query itself. It narrows candidate quality before heuristic scoring begins.
    def build_search_query(self, artist: str, song: str) -> str:
        """Build a focused Spotify search query from the parsed row values."""

        artist_query = artist.strip()
        song_query = song.strip()

        if artist_query and song_query:
            return f'track:"{song_query}" artist:"{artist_query}"'

        return f"{artist_query} {song_query}".strip()

    def build_search_queries(
        self,
        artist: str,
        song: str,
        *,
        original_title: str = "",
        artist_source: str = "",
    ) -> list[str]:
        """Build a small set of progressively looser Spotify search queries.

        The first query stays strict. Additional queries are reserved for
        uploader-fallback rows, where the parsed artist is known to be weaker
        and we can justify spending a couple of targeted recovery attempts.
        """

        queries: list[str] = [self.build_search_query(artist, song)]

        canonical_song = self._canonicalize_song_title(song)
        if canonical_song and canonical_song != self._normalize_text(song):
            queries.append(f'track:"{canonical_song}" artist:"{artist.strip()}"')

        contributor_names = list(self._extract_contributors(artist, song))
        if canonical_song and contributor_names:
            primary_contributor = max(contributor_names, key=len)
            queries.append(f'track:"{canonical_song}" artist:"{primary_contributor}"')

        if canonical_song:
            queries.append(f'track:"{canonical_song}"')
        queries.append(song.strip())

        if artist_source != "Uploader Fallback":
            return self._dedupe_queries(queries)

        inferred_artist, inferred_song = self._infer_artist_from_trailing_mix_title(original_title)
        if inferred_artist and inferred_song:
            queries.append(self.build_search_query(inferred_artist, inferred_song))

        if canonical_song:
            queries.append(f'track:"{canonical_song}"')

        return self._dedupe_queries(queries)

    # Song title gets more weight than artist because SoundCloud artist metadata
    # is often inferred or uploader-driven, while the title usually carries the
    # strongest identity signal.
    WEAK_ARTIST_EVIDENCE_CAP = 0.49
    MINIMUM_ARTIST_EVIDENCE = 0.5

    def _score_candidate(
        self,
        source_artist: str,
        source_song: str,
        candidate: dict[str, Any],
    ) -> float:
        """Combine artist and title similarity into a single match score."""

        candidate_song = self._normalize_text(str(candidate.get("name", "")))
        candidate_artists = self._normalize_text(
            " ".join(
                artist_item.get("name", "")
                for artist_item in candidate.get("artists", [])
                if artist_item.get("name")
            )
        )

        normalized_source_song = self._normalize_text(source_song)
        normalized_source_artist = self._normalize_text(source_artist)
        canonical_source_song = self._canonicalize_song_title(source_song)
        canonical_candidate_song = self._canonicalize_song_title(str(candidate.get("name", "")))
        source_contributors = self._extract_contributors(source_artist, source_song)
        candidate_contributors = self._extract_contributors(
            " ".join(
                artist_item.get("name", "")
                for artist_item in candidate.get("artists", [])
                if artist_item.get("name")
            ),
            str(candidate.get("name", "")),
        )

        direct_song_score = SequenceMatcher(None, normalized_source_song, candidate_song).ratio()
        canonical_song_score = SequenceMatcher(
            None,
            canonical_source_song,
            canonical_candidate_song,
        ).ratio()
        title_token_overlap_score = self._score_title_token_overlap(
            canonical_source_song,
            canonical_candidate_song,
        )
        song_score = max(direct_song_score, canonical_song_score, title_token_overlap_score)

        direct_artist_score = SequenceMatcher(
            None,
            normalized_source_artist,
            candidate_artists,
        ).ratio()
        contributor_overlap_score = self._score_contributor_overlap(
            source_contributors,
            candidate_contributors,
        )
        artist_score = max(direct_artist_score, contributor_overlap_score)

        if canonical_source_song and canonical_source_song == canonical_candidate_song:
            song_score = max(song_score, 0.98)
        if source_contributors and source_contributors.issubset(candidate_contributors):
            artist_score = max(artist_score, 0.98)

        # Search broadening is useful for recall, but we still need a guardrail
        # against "same vibe, wrong record" matches. If the title is only
        # loosely similar and the artist evidence is weak, this candidate should
        # not survive on title fuzziness alone.
        if artist_score < 0.5 and contributor_overlap_score == 0.0:
            if canonical_source_song != canonical_candidate_song and title_token_overlap_score < 1.0:
                return 0.0

        score = (song_score * 0.65) + (artist_score * 0.35)

        # An exact title match is common across unrelated catalogs. When the
        # parsed SoundCloud artist does not resemble the Spotify artist at all,
        # cap the score below the acceptance threshold instead of letting title
        # similarity alone create a confident false positive.
        if (
            normalized_source_artist
            and artist_score < self.MINIMUM_ARTIST_EVIDENCE
            and contributor_overlap_score == 0.0
        ):
            return min(score, self.WEAK_ARTIST_EVIDENCE_CAP)

        return score

    @classmethod
    def _canonicalize_song_title(cls, value: str) -> str:
        """Reduce a song title to its identity-bearing core for comparison.

        SoundCloud titles often omit metadata that Spotify adds for catalog
        hygiene, such as featured artists or "Radio Edit" suffixes. Matching
        should reward shared song identity, not penalize the richer storefront
        representation.
        """

        normalized_value = value.strip()
        normalized_value = cls.FEATURE_BLOCK_PATTERN.sub("", normalized_value)
        normalized_value = cls.TRAILING_COLLABORATOR_TITLE_PATTERN.sub("", normalized_value)

        segments = cls.TITLE_SUFFIX_SEPARATOR_PATTERN.split(normalized_value)
        if len(segments) > 1:
            kept_segments = [segments[0]]
            for segment in segments[1:]:
                if not cls.TITLE_DECORATION_PATTERN.search(segment):
                    kept_segments.append(segment)
            normalized_value = " - ".join(kept_segments)

        normalized_value = re.sub(r"[\(\[]([^\)\]]+)[\)\]]", cls._strip_decorative_brackets, normalized_value)
        return cls._normalize_text(normalized_value)

    @classmethod
    def _strip_decorative_brackets(cls, match: re.Match[str]) -> str:
        """Remove bracketed title text when it is descriptive rather than identifying."""

        content = match.group(1)
        if cls.FEATURE_PATTERN.search(content) or cls.TITLE_DECORATION_PATTERN.search(content):
            return ""
        return f" {content} "

    @classmethod
    def _extract_contributors(cls, artist: str, song: str) -> set[str]:
        """Extract likely contributor names from artist and featured-title text.

        Contributor overlap is a more stable signal than raw artist-string
        similarity because Spotify and SoundCloud express collaborations with
        different punctuation, ordering, and placement of featured artists.
        """

        contributor_names = cls._split_artist_names(artist)
        feature_match = re.search(
            r"\b(?:feat|ft|featuring|with|w/)\.?\s+(.+?)(?:$|\)|\]|\s-\s)",
            song,
            re.IGNORECASE,
        )
        if feature_match:
            contributor_names.update(cls._split_artist_names(feature_match.group(1)))
        return contributor_names

    @classmethod
    def _split_artist_names(cls, value: str) -> set[str]:
        """Split a composite artist string into normalized contributor tokens."""

        normalized_value = cls._normalize_text(value)
        contributors = {
            token.strip()
            for token in cls.ARTIST_SPLIT_PATTERN.split(normalized_value)
            if token.strip()
        }
        return {token for token in contributors if len(token) > 1}

    @staticmethod
    def _score_contributor_overlap(source: set[str], candidate: set[str]) -> float:
        """Score how completely the candidate covers the source contributors.

        Artist credits across platforms are messy in predictable ways: `vs`
        separators, featured-artist placement, punctuation differences, and the
        occasional one-character spelling drift. The goal here is not to demand
        byte-for-byte equality, but to answer the more useful question: "does
        this Spotify result appear to contain the same collaborating artists?"
        """

        if not source or not candidate:
            return 0.0

        matched_source_contributors = 0
        for source_name in source:
            best_similarity = max(
                (SequenceMatcher(None, source_name, candidate_name).ratio() for candidate_name in candidate),
                default=0.0,
            )
            if best_similarity >= 0.84:
                matched_source_contributors += 1

        return matched_source_contributors / len(source)

    @staticmethod
    def _score_title_token_overlap(source_title: str, candidate_title: str) -> float:
        """Measure title agreement using exact normalized tokens.

        Sequence similarity is good at spotting close spellings, but it can
        over-credit pairs like `danger` and `dangerous`. Token overlap is a
        better guardrail for deciding whether two titles refer to the same
        underlying song identity.
        """

        source_tokens = {token for token in source_title.split() if token}
        candidate_tokens = {token for token in candidate_title.split() if token}
        if not source_tokens or not candidate_tokens:
            return 0.0

        if source_tokens == candidate_tokens:
            return 1.0

        overlap = source_tokens.intersection(candidate_tokens)
        if not overlap:
            return 0.0

        return len(overlap) / max(len(source_tokens), len(candidate_tokens))

    @classmethod
    def _infer_artist_from_trailing_mix_title(cls, original_title: str) -> tuple[str | None, str | None]:
        """Recover `artist` and `song` from uploader-fallback titles when possible.

        Some uploads append the actual artist after a mix descriptor instead of
        placing it before a dash, e.g. `Burner (Original Mix) Leik`. This is
        too specialized to bake into the primary parser, but it is useful as a
        second-pass search hint once we already know the row came from uploader
        fallback.
        """

        normalized_title = " ".join(original_title.strip().split())
        mix_match = cls.MIX_DESCRIPTOR_PATTERN.search(normalized_title)
        if mix_match is None:
            return None, None

        trailing_text = normalized_title[mix_match.end():].strip(" -")
        if not trailing_text:
            return None, None
        if len(trailing_text.split()) > 4:
            return None, None

        leading_text = normalized_title[:mix_match.start()].strip(" -")
        mix_text = mix_match.group(1).strip()
        if not leading_text or not mix_text:
            return None, None

        inferred_song = f"{leading_text} ({mix_text})"
        return trailing_text, inferred_song

    @staticmethod
    def _dedupe_queries(queries: list[str]) -> list[str]:
        """Preserve query order while removing duplicate search attempts."""

        seen_queries: set[str] = set()
        unique_queries: list[str] = []
        for query in queries:
            normalized_query = query.strip()
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            unique_queries.append(normalized_query)
        return unique_queries

    @staticmethod
    def _normalize_text(value: str) -> str:
        """Normalize punctuation and spacing before fuzzy comparison."""

        normalized_value = value.lower().strip()
        normalized_value = re.sub(r"[^\w\s]", " ", normalized_value)
        normalized_value = re.sub(r"\s+", " ", normalized_value)
        return normalized_value

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Convert a possibly-missing API field into a nullable string."""

        if value is None:
            return None
        return str(value)
