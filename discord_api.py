"""A small Discord REST client for a bot (API v10): read a server, post, make channels and threads.
There is no delete, kick, ban or role change here on purpose. Every message goes out with mentions turned
off, so nothing Hisho posts pings @everyone or a person.

HTTP goes through one function, ``http(method, url, headers, body, timeout) -> (status, headers, data)``,
so tests can stand in for Discord."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable

API = "https://discord.com/api/v10"
UA = "DiscordBot (hisho-addon-discord, 0.1)"   # the form Discord asks bots to send
TEXT, VOICE, CATEGORY, NEWS, FORUM = 0, 2, 4, 5, 15
KINDS = {TEXT: "text", VOICE: "voice", CATEGORY: "category", NEWS: "announcement", 13: "stage", FORUM: "forum"}
#: what the bot needs for everything the add-on does (bit -> name); anything missing is shown on the page
NEEDED = {10: "View Channels", 11: "Send Messages", 4: "Manage Channels", 29: "Manage Webhooks", 16: "Read Message History",
          35: "Create Public Threads", 38: "Send Messages in Threads", 14: "Embed Links"}
RISKY = {3: "Administrator", 1: "Kick Members", 2: "Ban Members", 28: "Manage Roles", 5: "Manage Server"}
NO_MENTIONS = {"parse": []}


class DiscordError(RuntimeError):
    """``kind``: unreachable | token | access | http."""

    def __init__(self, msg: str, kind: str = "http", status: int = 0) -> None:
        super().__init__(msg)
        self.kind, self.status = kind, status


def http(method: str, url: str, headers: dict[str, str], body: Any, timeout: float) -> tuple[int, dict, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as f:
            raw = f.read()
            return f.status, dict(f.headers), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()[:400]
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"message": raw.decode(errors="replace")}
        return e.code, dict(e.headers or {}), payload
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise DiscordError(f"Discord not reachable: {getattr(e, 'reason', e)}", "unreachable") from None


def clean_name(name: str) -> str:
    """What Discord makes of a text channel's name: lower case, dashes, no spaces."""
    return re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower().lstrip("#")).strip("-")[:100]


class Bot:
    def __init__(self, token: Callable[[], str], transport: Callable[..., Any] | None = None, timeout: float = 20) -> None:
        self._token = token
        self.transport = transport or (lambda *a: http(*a))   # looked up per call, so tests can replace http
        self.timeout = timeout

    def call(self, method: str, path: str, body: Any = None, reason: str = "") -> Any:
        assert method in ("GET", "POST", "PATCH", "PUT"), "the add-on never deletes"
        headers = {"Authorization": f"Bot {self._token().strip()}"}
        if reason:
            headers["X-Audit-Log-Reason"] = reason[:200]
        for _attempt in range(3):
            status, hdrs, data = self.transport(method, API + path, headers, body, self.timeout)
            if status == 429:  # rate limited: wait what Discord says (capped) and try again
                time.sleep(min(float((data or {}).get("retry_after") or 1), 10))
                continue
            if status == 401:
                raise DiscordError("Discord refused the bot token (reset or deleted?)", "token", 401)
            if status in (403, 404) and path.startswith("/guilds/"):
                raise DiscordError(f"the bot can't see that server (not in it, or kicked): HTTP {status}",
                                   "access", status)
            if status >= 400:
                raise DiscordError(f"{method} {path}: HTTP {status} {(data or {}).get('message') or ''}".strip(),
                                   "http", status)
            return data
        raise DiscordError(f"{method} {path}: still rate limited", "http", 429)

    # ── reads ─────────────────────────────────────────────────────────────
    def me(self) -> dict[str, Any]:
        return self.call("GET", "/users/@me")

    def guild(self, gid: str) -> dict[str, Any]:
        return self.call("GET", f"/guilds/{gid}?with_counts=true")

    def channels(self, gid: str) -> list[dict[str, Any]]:
        return self.call("GET", f"/guilds/{gid}/channels") or []

    def member(self, gid: str, uid: str) -> dict[str, Any]:
        return self.call("GET", f"/guilds/{gid}/members/{uid}")

    def members(self, gid: str) -> list[dict[str, Any]]:
        """Needs the bot's Server Members switch (privileged); the caller copes without."""
        return self.call("GET", f"/guilds/{gid}/members?limit=200") or []

    # ── writes (never a delete) ───────────────────────────────────────────
    def post(self, channel_id: str, text: str) -> dict[str, Any]:
        return self.call("POST", f"/channels/{channel_id}/messages",
                         {"content": text[:2000], "allowed_mentions": NO_MENTIONS})

    def thread(self, channel_id: str, name: str, first: str = "") -> dict[str, Any]:
        t = self.call("POST", f"/channels/{channel_id}/threads", {"name": name[:100], "type": 11,
                                                                  "auto_archive_duration": 10080}, "Hisho")
        if first:
            self.post(t["id"], first)
        return t

    def new_channel(self, gid: str, name: str, parent: str | None = None, topic: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {"name": clean_name(name), "type": TEXT}
        if parent:
            body["parent_id"] = parent
        if topic:
            body["topic"] = topic[:1024]
        return self.call("POST", f"/guilds/{gid}/channels", body, "Hisho")


def permissions(guild: dict[str, Any], member: dict[str, Any]) -> int:
    """A member's server-wide permissions: @everyone plus each of its roles."""
    roles = {r["id"]: r for r in guild.get("roles") or []}
    total = int((roles.get(guild["id"]) or {}).get("permissions") or 0)
    for rid in member.get("roles") or []:
        total |= int((roles.get(rid) or {}).get("permissions") or 0)
    return total


def channel_permissions(base: int, channel: dict[str, Any], guild_id: str, member: dict[str, Any], uid: str) -> int:
    """What a member may do in one channel: its server permissions, then the channel's overwrites in Discord's
    order (@everyone, then its roles together, then the member itself). Administrator sees everything."""
    if base >> 3 & 1:
        return base
    ows = {o["id"]: o for o in channel.get("permission_overwrites") or []}
    perms = base
    if guild_id in ows:
        perms = (perms & ~int(ows[guild_id]["deny"])) | int(ows[guild_id]["allow"])
    allow = deny = 0
    for rid in member.get("roles") or []:
        if rid in ows:
            allow |= int(ows[rid]["allow"])
            deny |= int(ows[rid]["deny"])
    perms = (perms & ~deny) | allow
    if uid in ows:
        perms = (perms & ~int(ows[uid]["deny"])) | int(ows[uid]["allow"])
    return perms


def can(perms: int, *bits: int) -> bool:
    return all(perms >> b & 1 for b in bits)


def find_channel(channels: list[dict[str, Any]], want: str, kinds: tuple[int, ...] = (TEXT, NEWS)) -> dict[str, Any]:
    """A channel by id, name or #name (text and announcement channels only, unless ``kinds`` says)."""
    w = str(want).strip()
    for c in channels:
        if c["type"] in kinds and (c["id"] == w or c["name"] == clean_name(w) or c["name"] == w.lstrip("#")):
            return c
    raise DiscordError(f"no channel {want!r} (names: {', '.join(c['name'] for c in channels if c['type'] in kinds)})")
