# Discord (Hisho add-on)

## What it does

Lets Hisho run your Discord servers through **your own private bot**, never through another assistant's:

- **The card** (overview), one line per server, e.g. `Team-Server: 12 channels · 5 members`, and a warning
  in Needs you if Discord refuses the bot's token, the bot is no longer in the server, or it lacks a
  permission it needs (named, with where to turn it on).
- **Its page** (**Add-ons > Discord**): members (online count), roles, the member list (only with the bot's
  Server Members switch on), every channel grouped by category with a link to open it in Discord, and a
  note if the bot has more power than it needs (Administrator, kick, ban, roles).
- **Buttons** (unless the entry says `allow_writes: false`), each after you confirm: **post** in a channel,
  start a **thread** (`name | first message`), make a **new channel** (`name`, or `name in CATEGORY`).
  From a terminal: `hisho addon do discord main ch-<channel id> post --input "Deploy done"`.
- **For other add-ons** it provides `chat_messages`: an add-on that wants to tell a channel something (the
  Vikunja add-on's task changes, CI results, deploy notices) calls `post_message(channel, text)` and never
  names Discord, so another chat tool could take its place.
- **What it never does**: delete anything, kick, ban, or change roles or server settings: there is no such
  call in it. Every post goes out with mentions off, so nothing it sends pings @everyone or a person.

## What it needs

- You need:
  - A Discord server you manage
  - Your own private Discord bot (the form links to Discord's Developer Portal; Test gives the link that adds it to your server)
- Runs on: the Core machine, inside Hisho Core
- One entry per Discord server, each with:
  - `token` (password, kept as a local secret, required)
  - `server` (str, optional)
  - `allow_writes` (bool, optional)
  - `note` (str, optional)
- Provides: `chat_messages`

## How to install

On the dashboard: **Add-ons > Store > Discord > Install**. Or from a terminal:

```bash
hisho addon install discord
```

Hisho takes the newest version from this repository, copies it to the machine it runs on and turns
it on. Updates show as **Update available** on its Store card; **Roll back** returns to the version
before.

## How to use

Its card has one line per server and warns if the bot lost access or a permission. Its page (**Add-ons > Discord**) shows channels, roles and members; **post**, **thread** and **new channel** ask first. Other add-ons post through it (it provides `chat_messages`).

## Settings

1. **Make the bot** at https://discord.com/developers/applications: New Application > Bot. Turn **Public
   Bot** off (first set Installation > Install Link to *None*, or Discord refuses to save). Reset Token and copy it.
2. **Add it**: Add-ons > Discord > **+ add**, paste the token, leave Server ID empty and press **Test**.
   - If the bot is in one server, Hisho fills in its Server ID. Press **Add**.
   - If it is in none, Test gives the ready invite link (the bot's application id filled in, asking for exactly
     what the add-on needs: `permissions=309774601232` = View Channels, Manage Channels, Manage Webhooks, Send
     Messages, Send Messages in Threads, Create Public Threads, Embed Links, Read Message History; not
     Administrator). Open it, choose your server, Authorize, and press Test again.
   - If it is in several, Test lists them; type the Server ID of the one this entry is for.
   The pasted token is kept as a local secret on the Core machine (or type the name of a saved secret, e.g.
   `DISCORD_BOT_TOKEN`). Change its permissions later in Server Settings > Roles > your bot.

Or in `~/Hisho/System/Config/Addons/discord.yaml`:

```yaml
entries:
  main:
    token: DISCORD_BOT_TOKEN       # the secret's NAME, never the token
    server: "123456789012345678"   # Server ID (Developer Mode on, right-click the server > Copy Server ID)
    allow_writes: true             # false = read only, and other add-ons can't post through it
```

## How to remove

**Add-ons > Store > Discord > Remove**, or `hisho addon remove discord`. Your settings file stays,
so installing it again picks up where you left off.

## License

Source-available under the [PolyForm Shield License 1.0.0](LICENSE.md): free to use, change and share,
for any purpose except offering a product that competes with Hisho (reselling it, for example).
