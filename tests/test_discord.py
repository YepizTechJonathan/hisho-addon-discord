"""Run with Hisho's venv at the repository's top: ~/code/hisho/.venv/bin/python -m pytest -q

FakeDiscord answers like Discord's REST API v10 did on 2026-10-21 for a server with categories, a voice
channel and a bot role, applies writes in memory and records every request."""
import json
from pathlib import Path

import pytest

from hisho import addon_store, addons

HERE = Path(__file__).resolve().parents[1]
GID, BOT, ROLE = "900", "500", "77"
NEEDED = sum(1 << b for b in (4, 10, 11, 14, 16, 29, 35, 38))


class FakeDiscord:
    def __init__(self):
        self.calls, self.posts, self.made = [], [], []
        self.role_perms = NEEDED
        self.token_ok, self.in_guild, self.members_intent = True, True, False
        self.limited_once = False
        self.channels = [
            {"id": "1", "type": 4, "name": "pipeline", "position": 2},
            {"id": "2", "type": 4, "name": "start-here", "position": 0},
            {"id": "10", "type": 0, "name": "vikunja-tasks", "parent_id": "1", "position": 1, "topic": "Task changes"},
            {"id": "11", "type": 0, "name": "dev-testing", "parent_id": "1", "position": 0},
            {"id": "12", "type": 0, "name": "welcome", "parent_id": "2", "position": 0},
            {"id": "13", "type": 2, "name": "War Room", "parent_id": "2", "position": 1},
        ]

    def __call__(self, method, url, headers, body, timeout):
        path = url.split("/api/v10", 1)[1]
        self.calls.append((method, path))
        if self.limited_once:
            self.limited_once = False
            return 429, {}, {"retry_after": 0.01}
        if headers["Authorization"] != "Bot value-of-DISCORD_BOT_TOKEN" or not self.token_ok:
            return 401, {}, {"message": "401: Unauthorized"}
        if path == "/users/@me":
            return 200, {}, {"id": BOT, "username": "Hisho", "bot": True}
        if path.startswith(f"/guilds/{GID}") and not self.in_guild:
            return 403, {}, {"message": "Missing Access"}
        if path == f"/guilds/{GID}?with_counts=true":
            return 200, {}, {"id": GID, "name": "Team-Server", "approximate_member_count": 5,
                             "approximate_presence_count": 2,
                             "roles": [{"id": GID, "name": "@everyone", "permissions": "0", "position": 0},
                                       {"id": ROLE, "name": "Hisho", "permissions": str(self.role_perms), "position": 1},
                                       {"id": "78", "name": "Developer", "permissions": "0", "position": 2}]}
        if path == f"/guilds/{GID}/members/{BOT}":
            return 200, {}, {"roles": [ROLE]}
        if path.startswith(f"/guilds/{GID}/members?"):
            if not self.members_intent:
                return 403, {}, {"message": "Missing Access"}
            return 200, {}, [{"user": {"username": "jane"}, "roles": ["78"]}, {"user": {"username": "Hisho", "bot": True},
                                                                               "roles": [ROLE]}]
        if path == f"/guilds/{GID}/channels" and method == "GET":
            return 200, {}, self.channels
        if path == f"/guilds/{GID}/channels" and method == "POST":
            c = {"id": str(100 + len(self.made)), "position": 9, **body}
            self.channels.append(c)
            self.made.append(c)
            return 201, {}, c
        if path.startswith("/channels/") and path.endswith("/messages"):
            self.posts.append((path.split("/")[2], body))
            return 200, {}, {"id": f"m{len(self.posts)}"}
        if path.startswith("/channels/") and path.endswith("/threads"):
            return 201, {}, {"id": "t1", "name": body["name"]}
        return 404, {}, {"message": f"no route {method} {path}"}


ENTRY = {"team": {"token": "DISCORD_BOT_TOKEN", "server": GID}}


@pytest.fixture
def mod(addon):
    return addons.provider(addon)


@pytest.fixture
def fake(mod, monkeypatch):
    f = FakeDiscord()
    monkeypatch.setattr(mod.dc, "http", f)
    return f


def press(mod, ctx, item, action, typed="", entries=ENTRY):
    ctx.input = typed
    return mod.act(entries, ctx, "team", item, action)


def test_manifest_is_valid_and_readme_matches(addon):
    assert addons.validate_manifest(addon.manifest) == []
    assert addon_store.readme_problems(HERE) == []


def test_no_entries_is_unknown_not_an_alert(addon, ctx_for):
    assert addons.summarize(addon, ctx_for(addon))["state"] in ("unknown", "ok")
    assert addons.provider(addon).summary({}, ctx_for(addon))["state"] == "unknown"


def test_summary(mod, fake, addon, ctx_for):
    s = mod.summary(ENTRY, ctx_for(addon))
    assert s == {"state": "ok", "headline": "Team-Server: 3 channels · 5 members", "problems": []}


@pytest.mark.parametrize("break_it,title", [("token", "team: Discord refused the bot token"),
                                            ("guild", "team: the bot is not in the server")])
def test_bad_token_or_kicked_bot_is_a_warning(mod, fake, addon, ctx_for, break_it, title):
    if break_it == "token":
        fake.token_ok = False
    else:
        fake.in_guild = False
    s = mod.summary(ENTRY, ctx_for(addon))
    assert s["state"] == "warn" and [p["title"] for p in s["problems"]] == [title]
    assert "value-of" not in json.dumps(s)
    assert mod.test(ENTRY["team"], ctx_for(addon))["ok"] is False


def test_missing_permission_is_named(mod, fake, addon, ctx_for):
    fake.role_perms = NEEDED & ~(1 << 29)
    s = mod.summary(ENTRY, ctx_for(addon))
    assert [p["title"] for p in s["problems"]] == ["Team-Server: the bot lacks Manage Webhooks"]
    assert mod.test(ENTRY["team"], ctx_for(addon))["error"].endswith("but it lacks Manage Webhooks")


def test_rate_limit_is_waited_out(mod, fake, addon, ctx_for):
    fake.limited_once = True
    assert mod.summary(ENTRY, ctx_for(addon))["state"] == "ok"


def test_details_page(mod, fake, addon, ctx_for):
    [sec] = mod.details(ENTRY, ctx_for(addon))
    assert sec["title"] == "Team-Server" and sec["state"] == "ok"
    assert sec["facts"][1] == "Roles: Developer, Hisho"
    assert "Server Members switch" in sec["facts"][2]
    assert [it["name"] for it in sec["items"]] == ["New channel in Team-Server", "#welcome", "War Room",
                                                    "#dev-testing", "#vikunja-tasks"]
    tasks = sec["items"][-1]
    assert tasks["facts"] == ["pipeline · text", "Task changes"]
    assert [a["id"] for a in tasks["actions"]] == ["post", "thread"]
    assert sec["items"][2]["actions"] == []                     # nothing to press on a voice channel
    fake.members_intent = True
    assert mod.details(ENTRY, ctx_for(addon))[0]["facts"][2] == "Members: Hisho (bot) [Hisho]; jane [Developer]"
    fake.role_perms = NEEDED | (1 << 3)
    assert "more than it needs: Administrator" in " ".join(mod.details(ENTRY, ctx_for(addon))[0]["facts"])
    ro = mod.details({"team": {**ENTRY["team"], "allow_writes": False}}, ctx_for(addon))[0]
    assert all(not it["actions"] for it in ro["items"])


def test_buttons(mod, fake, addon, ctx_for):
    ctx = ctx_for(addon)
    assert press(mod, ctx, "ch-10", "post", "Hello @everyone")["message"] == "posted in #vikunja-tasks"
    assert fake.posts == [("10", {"content": "Hello @everyone", "allowed_mentions": {"parse": []}})]   # no ping
    assert press(mod, ctx, "ch-11", "thread", "Build 42 | starting")["message"] == \
        "thread Build 42 started in #dev-testing"
    assert fake.posts[-1] == ("t1", {"content": "starting", "allowed_mentions": {"parse": []}})
    assert press(mod, ctx, "server", "new-channel", "Prod Deploys in pipeline")["message"] == \
        "made #prod-deploys in pipeline"
    assert fake.made[-1]["parent_id"] == "1" and fake.made[-1]["name"] == "prod-deploys"
    assert "already there" in press(mod, ctx, "server", "new-channel", "prod-deploys in pipeline")["error"]
    assert "no channel" in press(mod, ctx, "server", "new-channel", "x in nowhere")["error"]


def test_buttons_never_reach_outside_the_server_or_delete(mod, fake, addon, ctx_for):
    ctx = ctx_for(addon)
    assert "no channel" in press(mod, ctx, "ch-999", "post", "hi")["error"]      # another server's channel
    assert "not a button" in press(mod, ctx, "ch-10", "delete", "x")["error"]
    assert "read only" in press(mod, ctx, "ch-10", "post", "hi",
                                {"team": {**ENTRY["team"], "allow_writes": False}})["error"]
    assert fake.posts == []
    assert not any(m == "DELETE" for m, _ in fake.calls)
    assert "DELETE" not in (HERE / "discord_api.py").read_text()


def test_other_add_ons_post_through_the_capability(mod, fake, addon, ctx_for, monkeypatch):
    addons.set_entry(addon, "team", ENTRY["team"])
    addons.enable("discord")
    found, module, ents = addons.capability("chat_messages")
    assert found.name == "discord"
    res = module.post_message(ents, ctx_for(addon), "#vikunja-tasks", "📋 task changes")
    assert res == {"ok": True, "id": "m1", "message": "posted in #vikunja-tasks"}
    assert module.post_message(ents, ctx_for(addon), "nope", "x")["ok"] is False
    two = {**ENTRY, "other": ENTRY["team"]}
    assert "say which" in module.post_message(two, ctx_for(addon), "vikunja-tasks", "x")["error"]
    ro = {"team": {**ENTRY["team"], "allow_writes": False}}
    assert "read only" in module.post_message(ro, ctx_for(addon), "vikunja-tasks", "x")["error"]
    assert len(fake.posts) == 1


def test_the_token_comment_names_the_bot_and_what_it_may_do(mod, fake, addon, ctx_for):
    what = mod.describe_secret(ENTRY["team"], ctx_for(addon))
    assert what.startswith("Discord bot token of Hisho (application 500), in server Team-Server. Its permissions there: ")
    assert "Manage Webhooks" in what and "Administrator" not in what


PRIVATE = [{"id": GID, "type": 0, "allow": "0", "deny": str(1 << 10)},          # hidden from @everyone
           {"id": "78", "type": 0, "allow": str(1 << 10), "deny": "0"}]         # open to Developer only


def test_a_channel_the_bot_cannot_open_is_shown_and_never_posted_to(mod, fake, addon, ctx_for):
    ctx = ctx_for(addon)
    fake.channels[2]["permission_overwrites"] = PRIVATE                         # vikunja-tasks
    assert mod.summary(ENTRY, ctx)["headline"] == "Team-Server: 3 channels · 5 members · the bot can't post in 1"
    items = {it["name"]: it for it in mod.details(ENTRY, ctx)[0]["items"]}
    shut = items["#vikunja-tasks"]
    assert shut["state"] == "off" and shut["actions"] == []
    assert "the bot can't open it: add the Hisho role" in shut["facts"][-1]
    assert [a["id"] for a in items["#dev-testing"]["actions"]] == ["post", "thread"]
    res = mod.post_message(ENTRY, ctx, "vikunja-tasks", "x")
    assert res["ok"] is False and "can't post in #vikunja-tasks" in res["error"] and fake.posts == []
    # let the bot's role in (what the owner does in Discord): it can post again
    fake.channels[2]["permission_overwrites"] = PRIVATE + [{"id": ROLE, "type": 0, "allow": str(1 << 10), "deny": "0"}]
    assert mod.post_message(ENTRY, ctx, "vikunja-tasks", "x")["ok"] is True


def test_channel_permission_order(mod):
    dc = mod.dc
    base = (1 << 10) | (1 << 11)
    member = {"roles": ["r1", "r2"]}
    ch = {"permission_overwrites": [{"id": "g", "allow": "0", "deny": str(1 << 10)},
                                    {"id": "r1", "allow": str(1 << 10), "deny": "0"},
                                    {"id": "r2", "allow": "0", "deny": str(1 << 11)},
                                    {"id": "me", "allow": str(1 << 11), "deny": "0"}]}
    assert dc.channel_permissions(base, ch, "g", member, "me") == base          # role allow beats @everyone deny;
    assert dc.channel_permissions(base, ch, "g", member, "other") == 1 << 10    # member allow beats role deny
    assert dc.channel_permissions(1 << 3, ch, "g", {"roles": []}, "x") == 1 << 3  # admin: no overwrite applies
