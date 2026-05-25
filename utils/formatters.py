"""
Message formatting helpers.
All bot messages are composed here for consistency.
"""

from typing import List, Optional
from models import Track, UserSession


def fmt_track_card(track: Track, index: Optional[int] = None) -> str:
    """Format a single track as a Markdown card."""
    prefix = f"*{index}.* " if index is not None else ""
    lines = [
        f"{prefix}🎵 *{_esc(track.title)}*",
        f"👤 {_esc(track.artist)}",
    ]
    if track.album:
        lines.append(f"💿 {_esc(track.album)}")
    if track.duration:
        lines.append(f"⏱ {track.duration_str}")
    if track.genre:
        lines.append(f"🎸 {_esc(track.genre)}")
    if track.preview_url:
        lines.append(f"\n[🎧 Preview]({track.preview_url})")
    return "\n".join(lines)


def fmt_now_playing(track: Track, queue_length: int = 0) -> str:
    """Format the now-playing message."""
    lines = [
        "🎶 *Now Playing*",
        "",
        f"🎵 *{_esc(track.title)}*",
        f"👤 {_esc(track.artist)}",
    ]
    if track.album:
        lines.append(f"💿 {_esc(track.album)}")
    if track.duration:
        lines.append(f"⏱ {track.duration_str}")
    if track.preview_url:
        lines.append(f"\n[🎧 Stream Preview]({track.preview_url})")
    if queue_length > 0:
        lines.append(f"\n📋 *{queue_length} track{'s' if queue_length > 1 else ''} in queue*")
    return "\n".join(lines)


def fmt_queue(session: UserSession) -> str:
    """Format the queue overview."""
    if not session.queue and not session.current_track:
        return "📋 Your queue is empty. Use /search or /recommend to add tracks!"

    lines = ["📋 *Your Queue*\n"]

    if session.current_track:
        t = session.current_track
        lines.append(f"▶️ *Now:* {_esc(t.artist)} — {_esc(t.title)}\n")

    if session.queue:
        lines.append(f"*Up next ({len(session.queue)} tracks):*")
        for i, item in enumerate(session.queue[:10], 1):
            t = item.track
            lines.append(f"`{i:2}.` {_esc(t.artist)} — {_esc(t.title)}")
        if len(session.queue) > 10:
            lines.append(f"_...and {len(session.queue) - 10} more_")
    else:
        lines.append("_Queue is empty after current track_")

    return "\n".join(lines)


def fmt_history(session: UserSession, limit: int = 10) -> str:
    """Format recent play history."""
    if not session.history:
        return "📚 No play history yet. Start listening with /search or /trending!"

    lines = [f"📚 *Recently Played* ({session.play_count} total)\n"]
    for i, track in enumerate(session.history[:limit], 1):
        liked = " ❤️" if track.liked else ""
        lines.append(f"`{i:2}.` {_esc(track.artist)} — {_esc(track.title)}{liked}")
    return "\n".join(lines)


def fmt_recommendations(tracks: List[Track], title: str = "🎯 Recommended For You") -> str:
    """Format a list of recommended tracks."""
    if not tracks:
        return "😔 Couldn't find recommendations right now. Try /trending instead!"
    lines = [f"{title}\n"]
    for i, t in enumerate(tracks, 1):
        lines.append(f"`{i}.` *{_esc(t.title)}* — {_esc(t.artist)}")
    return "\n".join(lines)


def fmt_search_results(tracks: List[Track], query: str) -> str:
    """Format search result list."""
    if not tracks:
        return f"😔 No results for *{_esc(query)}*. Try a different search term."
    lines = [f"🔍 Results for *{_esc(query)}*\n"]
    for i, t in enumerate(tracks, 1):
        dur = f" `{t.duration_str}`" if t.duration else ""
        lines.append(f"`{i}.` *{_esc(t.title)}* — {_esc(t.artist)}{dur}")
    return "\n".join(lines)


def _esc(text: str) -> str:
    """Escape Markdown special chars for Telegram MarkdownV1."""
    if not text:
        return ""
    # Only escape chars that break Telegram Markdown rendering
    for ch in ["*", "_", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text
