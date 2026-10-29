# Changelog

## 0.2.0

- Paste the bot token and press Test: Hisho finds the server the bot is in and fills in its Server ID (Server ID is
  now optional). In none, Test gives the one-click invite link with the bot's application id and exactly the
  permissions the add-on needs (309774601232); in several, it lists them. A missing permission or a server the
  bot isn't in says where to fix it, with the same link.
- The token can be pasted (kept as a local secret) instead of saved as a secret first; a secret's name still works.

## 0.1.4

- Every field on its setup form says in plain words what it is, and links to where to get it (addon.yaml `help:`, shown by Hisho's dashboard).

## 0.1.3

- README says what you need (addon.yaml you_need) and how to use it; the README check requires both.

## 0.1.2

- Works out what the bot may do in each channel (its permission overwrites): the card says how many channels
  it can't post in, the page marks each one and says how to let it in, and `post_message` refuses up front
  with that fix instead of Discord's "Missing Access".

## 0.1.1

- The bot token's comment in the secrets store says which bot, which server and its permissions there
  (`hisho secret comment NAME --write --force`).

## 0.1.0

- First version: per server the channels by category, roles, members, the bot's missing or excess
  permissions; buttons to post, start a thread and make a channel; provides `chat_messages`
  (`post_message`) for other add-ons. Mentions always off; no delete, kick, ban or role call exists.
