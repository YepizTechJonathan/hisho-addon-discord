"""Discord integration for Hisho (see addon.yaml). Runs inside Core; talks to Discord's REST API as a bot
with discord_api.py (next to this file), which has no delete, kick, ban or role call at all.

It provides ``chat_messages`` (``post_message``), so other add-ons (Vikunja task changes, CI, deploys) post
to a channel without naming Discord. Every post goes out with mentions off.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location("hisho_addon_discord_api", Path(__file__).with_name("discord_api.py"))
dc = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(dc)


def bot(entry: dict[str, Any], ctx: Any) -> Any:
    return dc.Bot(lambda: ctx.secret(entry["token"]))


def writes_allowed(entry: dict[str, Any]) -> bool:
    return entry.get("allow_writes") is not False


def _problem(name: str, exc: Exception) -> dict[str, Any]:
    kind = getattr(exc, "kind", "") or "error"
    title = {"unreachable": "Can't reach Discord", "token": f"{name}: Discord refused the bot token",
             "access": f"{name}: the bot is not in the server"}.get(kind, f"{name}: Discord answered an error")
    return {"entry": name, "severity": "warn", "key": kind, "title": title, "detail": str(exc)}


def look(b: Any, entry: dict[str, Any]) -> dict[str, Any]:
    gid = str(entry.get("server") or "")
    if not gid:
        raise dc.DiscordError("no server chosen yet: press Test on its form", "access")
    g = b.guild(gid)
    me = b.me()
    member = b.member(gid, me["id"])
    perms = dc.permissions(g, member)
    channels = b.channels(gid)
    for c in channels:   # what the bot may do in each channel, after its permission overwrites
        c["_perms"] = dc.channel_permissions(perms, c, gid, member, me["id"])
    return {"guild": g, "me": me, "perms": perms, "channels": channels,
            "missing": [n for bit, n in dc.NEEDED.items() if not perms >> bit & 1 and not perms >> 3 & 1],
            "risky": [n for bit, n in dc.RISKY.items() if perms >> bit & 1]}


def summary(entries: dict[str, dict[str, Any]], ctx: Any) -> dict[str, Any]:
    if not entries:
        return {"state": "unknown", "headline": "No Discord server yet", "problems": []}
    problems, heads = [], []
    for name, entry in entries.items():
        try:
            s = look(bot(entry, ctx), entry)
        except dc.DiscordError as exc:
            problems.append(_problem(name, exc))
            continue
        g = s["guild"]
        texts = [c for c in s["channels"] if c["type"] in (dc.TEXT, dc.NEWS)]
        shut = sum(1 for c in texts if not dc.can(c["_perms"], 10, 11))
        heads.append(f"{g['name']}: {len(texts)} channels · {g.get('approximate_member_count', '?')} members"
                     + (f" · the bot can't post in {shut}" if shut else ""))
        if s["missing"]:
            problems.append({"entry": name, "severity": "warn", "key": "permissions",
                             "title": f"{g['name']}: the bot lacks {', '.join(s['missing'])}",
                             "detail": "Server Settings > Roles > " + s["me"]["username"] + ": turn these on."})
    return {"state": "warn" if problems else "ok", "headline": " · ".join(heads) or "not answering",
            "problems": problems}


def _members(b: Any, gid: str, roles: dict[str, str]) -> str:
    try:
        people = b.members(gid)
    except dc.DiscordError:
        return "Members: the list needs the bot's Server Members switch (Developer Portal > Bot)"
    out = []
    for m in people:
        u = m.get("user") or {}
        tag = ", ".join(roles[r] for r in m.get("roles") or [] if r in roles)
        out.append((m.get("nick") or u.get("global_name") or u.get("username") or "?")
                   + (" (bot)" if u.get("bot") else "") + (f" [{tag}]" if tag else ""))
    return "Members: " + "; ".join(sorted(out, key=str.lower))


def details(entries: dict[str, dict[str, Any]], ctx: Any) -> list[dict[str, Any]]:
    sections = []
    for name, entry in entries.items():
        b, writes = bot(entry, ctx), writes_allowed(entry)
        try:
            s = look(b, entry)
        except dc.DiscordError as exc:
            sections.append({"title": name, "entry": name, "state": "down", "facts": [str(exc)], "items": []})
            continue
        g, gid = s["guild"], str(entry["server"])
        roles = {r["id"]: r["name"] for r in g.get("roles") or [] if r["name"] != "@everyone"}
        facts = [f"{g.get('approximate_member_count', '?')} members ({g.get('approximate_presence_count', '?')} online) · "
                 f"bot {s['me']['username']} · " + ("buttons post and make channels" if writes else "read only"),
                 "Roles: " + ", ".join(r["name"] for r in sorted(g.get("roles") or [], key=lambda r: -r["position"])
                                       if r["name"] != "@everyone"),
                 _members(b, gid, roles)]
        if s["missing"]:
            facts.append("The bot lacks: " + ", ".join(s["missing"]))
        if s["risky"]:
            facts.append("The bot has more than it needs: " + ", ".join(s["risky"]))
        if entry.get("note"):
            facts.append(entry["note"])
        cats = {c["id"]: c["name"] for c in s["channels"] if c["type"] == dc.CATEGORY}
        items = [{"id": "server", "name": f"New channel in {g['name']}", "state": "up",
                  "facts": ["Type: name, or name in CATEGORY (" + ", ".join(cats.values()) + ")"],
                  "actions": [{"id": "new-channel", "label": "new channel",
                               "ask": "New text channel: name, or 'name in CATEGORY' (e.g. releases in pipeline)",
                               "confirm": f"Make a new channel in {g['name']}? Everyone who can see its category sees it."}]
                  if writes else []}]
        cat_pos = {c["id"]: c.get("position", 0) for c in s["channels"] if c["type"] == dc.CATEGORY}
        # as Discord lists them: channels with no category first, then category by category
        order = sorted((c for c in s["channels"] if c["type"] != dc.CATEGORY),
                       key=lambda c: (cat_pos.get(c.get("parent_id"), -1), c["type"] == dc.VOICE, c.get("position", 0)))
        for c in order:
            kind = dc.KINDS.get(c["type"], f"type {c['type']}")
            facts_c = [f"{cats.get(c.get('parent_id'), 'no category')} · {kind}"] + ([c["topic"]] if c.get("topic") else [])
            acts, shut = [], not dc.can(c["_perms"], 10)
            if shut:
                facts_c.append(f"the bot can't open it: add the {s['me']['username']} role (or a role it has) under "
                               "Edit Channel > Permissions, or on its category")
            elif c["type"] in (dc.TEXT, dc.NEWS) and not dc.can(c["_perms"], 11):
                facts_c.append("the bot can read it but not post in it")
            if writes and c["type"] in (dc.TEXT, dc.NEWS) and not shut and dc.can(c["_perms"], 11):
                acts = [{"id": "post", "label": "post", "ask": f"Message for #{c['name']}:",
                         "confirm": f"Post in #{c['name']}? Everyone in it sees it (no one is pinged)."},
                        {"id": "thread", "label": "thread", "ask": f"Thread name in #{c['name']} (then | a first message):",
                         "confirm": f"Start a thread in #{c['name']}?"}]
            items.append({"id": f"ch-{c['id']}", "name": ("#" if c["type"] in (dc.TEXT, dc.NEWS) else "") + c["name"],
                          "url": f"https://discord.com/channels/{gid}/{c['id']}", "state": "off" if shut else "up",
                          "facts": facts_c, "actions": acts})
        sections.append({"title": g["name"], "entry": name, "state": "warn" if s["missing"] else "ok",
                         "facts": facts, "items": items})
    return sections


def _app_id(b: Any, me: dict[str, Any]) -> str:
    """The bot's application id (the invite link's client_id); the bot's own user id if Discord won't say."""
    try:
        return str((b.application() or {}).get("id") or me["id"])
    except dc.DiscordError:
        return str(me["id"])


def test(entry: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """The page's Test (and Add) button: reads only. With no server typed, it finds the one the bot is in and
    fills it in; in none, it gives the ready invite link (one click: pick the server, Authorize)."""
    b = bot(entry, ctx)
    try:
        me = b.me()
    except dc.DiscordError as exc:
        out = {"ok": False, "error": str(exc)}
        if exc.kind == "token":
            out["explain"] = ("Discord refused that bot token. In the Developer Portal open your application > Bot > "
                              "Reset Token, copy the new token and paste it here (a token works only until it's reset).")
        return out
    fill = {}
    if not str(entry.get("server") or "").strip():
        try:
            servers = b.guilds()
        except dc.DiscordError as exc:
            return {"ok": False, "error": str(exc)}
        if not servers:
            link = dc.invite_link(_app_id(b, me))
            return {"ok": False, "error": f"the bot {me.get('username')} is in no server yet",
                    "explain": f"Your bot {me.get('username')} isn't in a server yet. Open this link, choose your "
                               f"server and press Authorize, then press Test again: {link}",
                    "invite": link}
        if len(servers) > 1:
            names = ", ".join(f"{g.get('name')} = {g.get('id')}" for g in servers[:10])
            return {"ok": False, "error": f"the bot is in {len(servers)} servers; type the Server ID of the one to add",
                    "explain": f"Your bot is in {len(servers)} servers. Type the Server ID of the one this entry is "
                               f"for ({names}), then press Test again. Add another entry for each other server."}
        fill = {"server": str(servers[0]["id"])}
        entry = {**entry, **fill}
    try:
        s = look(b, entry)
    except dc.DiscordError as exc:
        out = {"ok": False, "error": str(exc)}
        if exc.kind == "access":
            link = dc.invite_link(_app_id(b, me), str(entry.get("server") or ""))
            out.update(explain=f"Your bot {me.get('username')} isn't in that server (or can't see it). Open this "
                               f"link, press Authorize, then press Test again: {link}", invite=link)
        return out
    msg = f"Connected: bot {s['me']['username']} in {s['guild']['name']}"
    if s["missing"]:
        return {"ok": False, "error": f"{msg}, but it lacks {', '.join(s['missing'])}",
                "explain": f"The bot is in {s['guild']['name']} but lacks {', '.join(s['missing'])}. In Discord: "
                           f"Server Settings > Roles > {s['me']['username']}, turn those on (or invite it again "
                           f"with this link, which asks for exactly them: "
                           f"{dc.invite_link(_app_id(b, me), str(entry['server']))}), then press Test again."}
    if fill:
        msg += f" (found it: Server ID {fill['server']})"
    return {"ok": True, "message": msg, **({"fill": fill} if fill else {})}


def describe_secret(entry: dict[str, Any], ctx: Any) -> str:
    """The What line of the bot token's comment in the secrets store (``hisho secret comment NAME --write``)."""
    s = look(bot(entry, ctx), entry)
    has = [n for bit, n in {**dc.NEEDED, **dc.RISKY}.items() if s["perms"] >> bit & 1]
    return (f"Discord bot token of {s['me']['username']} (application {s['me']['id']}), in server {s['guild']['name']}."
            f" Its permissions there: {', '.join(has) or 'none'}")


def act(entries: dict[str, dict[str, Any]], ctx: Any, entry: str, item: str, action: str) -> dict[str, Any]:
    """A button: post, start a thread, make a channel. Nothing here deletes, kicks, bans or changes roles."""
    e = entries[entry]
    if not writes_allowed(e):
        return {"ok": False, "error": f"{entry} is read only (allow_writes: false)"}
    typed = str(getattr(ctx, "input", "") or "").strip()
    if action not in ("post", "thread", "new-channel"):
        return {"ok": False, "error": f"{action} is not a button of Discord"}
    if not typed:
        return {"ok": False, "error": "nothing typed"}
    b, gid = bot(e, ctx), str(e["server"])
    try:
        channels = b.channels(gid)
        if item == "server" and action == "new-channel":
            name, _, cat = typed.partition(" in ")
            parent = dc.find_channel(channels, cat, (dc.CATEGORY,))["id"] if cat.strip() else None
            if any(c["name"] == dc.clean_name(name) and c.get("parent_id") == parent for c in channels):
                return {"ok": False, "error": f"#{dc.clean_name(name)} is already there"}
            c = b.new_channel(gid, name, parent)
            return {"ok": True, "message": f"made #{c['name']}" + (f" in {cat.strip()}" if parent else "")}
        if not item.startswith("ch-"):
            return {"ok": False, "error": f"{action} on {item} is not a button of Discord"}
        ch = dc.find_channel(channels, item[3:])   # only a channel of this server
        if action == "post":
            m = b.post(ch["id"], typed)
            return {"ok": True, "message": f"posted in #{ch['name']}", "id": m.get("id")}
        name, _, first = typed.partition(" | ")
        t = b.thread(ch["id"], name.strip(), first.strip())
        return {"ok": True, "message": f"thread {t['name']} started in #{ch['name']}"}
    except dc.DiscordError as exc:
        return {"ok": False, "error": str(exc)}


# ── capability chat_messages (see hisho.addons) ──────────────────────────

def post_message(entries: dict[str, dict[str, Any]], ctx: Any, channel: str, text: str,
                 entry: str | None = None) -> dict[str, Any]:
    """Post ``text`` in ``channel`` (id, name or #name) of ``entry``'s server (the only one when not given).
    Mentions are off. Refused when that entry is read only."""
    if not entries:
        return {"ok": False, "error": "no Discord server set up"}
    if entry is None:
        if len(entries) > 1:
            return {"ok": False, "error": f"say which Discord server: {', '.join(entries)}"}
        entry = next(iter(entries))
    if entry not in entries:
        return {"ok": False, "error": f"no Discord server {entry} (have {', '.join(entries)})"}
    e = entries[entry]
    if not writes_allowed(e):
        return {"ok": False, "error": f"{entry} is read only (allow_writes: false)"}
    try:
        b = bot(e, ctx)
        s = look(b, e)
        ch = dc.find_channel(s["channels"], channel)
        if not dc.can(ch["_perms"], 10, 11):
            return {"ok": False, "error": f"the bot can't post in #{ch['name']}: give its role View Channel and Send "
                                          "Messages there (Edit Channel > Permissions, or its category)"}
        m = b.post(ch["id"], text)
    except dc.DiscordError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "id": m.get("id"), "message": f"posted in #{ch['name']}"}
