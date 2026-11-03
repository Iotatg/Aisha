# Aisha

A soft, girly group companion bot built from scratch on **kurigram + MongoDB**.
Aisha lives in your Telegram group: she chats, plays games, runs a small
economy, tracks presence, and keeps the room feeling alive.

Repository: https://github.com/Iotatg/Aisha

## Features

- AI chat companion with an offline sass fallback (never goes mute)
- Games: trivia, lucky box, word chain, type race, tic-tac-toe, bingo
- Economy: coins, gems, XP, daily streaks, leaderboards, gambling
- Profiles with level cards, XP bars and rank titles
- Fun & social pack: ship, charm, 8-ball, AFK, actions, truth/dare
- Sticker and GIF media replies (mood-matched, crowd-sourced packs)
- Presence tracking and welcome flows
- Owner admin commands with a global owner bypass
- Broadcast / DM with auto-delete

## Requirements

- Python 3.10 or newer
- MongoDB database
- `BOT_TOKEN` from [@BotFather](https://t.me/BotFather)
- `API_ID` and `API_HASH` from https://my.telegram.org (for kurigram)

## Quick start

```bash
# Clone the repository
git clone https://github.com/Iotatg/Aisha.git
cd Aisha

# Install dependencies
pip install -r requirements.txt

# Configure environment (all required)
export BOT_TOKEN="123:abc"
export API_ID="123456"
export API_HASH="your_api_hash"
export MONGO_URI="mongodb://localhost:27017"

# Start the bot
python3 main.py
```

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | Bot token from @BotFather |
| `API_ID` | Yes | MTProto api id from https://my.telegram.org |
| `API_HASH` | Yes | MTProto api hash from https://my.telegram.org |
| `MONGO_URI` | Yes | MongoDB connection string |
| `OWNER_ID` | Yes | Numeric Telegram id of the owner |
| `BOT_USERNAME` | No | Bot handle (default `im_aishabot`) |
| `AISHA_DB_NAME` | No | Mongo database name (default `aisha_bot`) |
| `AISHA_OPENROUTER_API_KEY` | No | AI provider key; offline sass answers if unset |
| `AISHA_GIPHY_API_KEY` | No | GIPHY key for GIF action replies |
| `PORT` | No | Health-server port (default `8080`) |

## Commands

### General
| Command | What it does |
| --- | --- |
| `/start` | Greeting card |
| `/help` | Full command map |
| `/about` | Bot info |
| `/ping` | Latency check |

### Economy
| Command | What it does |
| --- | --- |
| `/balance`, `/bal` | Coins, gems, XP, streak |
| `/daily` | Daily gift; streaks grow rewards, weekly bonus gem |
| `/pay <amt>` (reply) | Send coins to someone |
| `/leaders`, `/rich` | Top richest |
| `/gamble <amt>` | Double-or-nothing |
| `/flipcoin`, `/dice` | Just for fun |

### Profile
| Command | What it does |
| --- | --- |
| `/me`, `/profile` | Level card with XP bar and title |
| `/topxp` | XP leaderboard with level titles |

Titles: ɴᴇᴡʙɪᴇ → ᴄᴜᴛɪᴇ → ꜱᴛᴀʀʟᴇᴛ → Qᴜᴇᴇɴ → ʟᴇɢᴇɴᴅ.

### Games
| Command | Rules |
| --- | --- |
| `/trivia` | MCQ buttons; first correct tap wins coins + XP |
| `/luckybox <bet>` | Pick 1 of 3 boxes for a multiplier |
| `/wordchain <word>` | Last-letter chain; no repeats; last survivor takes the pot |
| `/typerace` | Type the shown sentence; fastest wins the most |
| `/racestop` | Abort a race |

### Fun
`/compliment` (reply), `/ship` (reply), `/8ball <q>`, `/hug`, `/pat`, `/afk [reason]`.

## Architecture

```text
aisha/
├── config.py            env-driven settings
├── main.py              entry point
├── core/
│   ├── db.py            lazy Motor handle, test-swappable
│   ├── money.py         single wallet layer: balances, gems, XP, levels
│   ├── app.py           handler registry (modules self-register)
│   └── helpers.py       mentions, coin formatting
├── handlers/            start, economy, profile, extras, owner, ...
│   └── games/           trivia, luckybox, wordchain, typerace
└── requirements.txt
```

Design notes:
- All balance mutations flow through `core/money.py` (`try_deduct` is atomic).
- Handler modules expose `register(add, filters, add_cb)`; `core/app.py` wires them.
- Small-caps text is hand-authored unicode, not generated at runtime.

## License

Released under the MIT License. See `LICENSE`.

Copyright (c) 2025-2026 Iota Coders.
