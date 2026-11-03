# Aisha — Render Environment Variables

Set these in the Render dashboard under the service's **Environment** tab.

## Required (secrets — never commit these)
| Key | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `API_ID` | MTProto api id from https://my.telegram.org |
| `API_HASH` | MTProto api hash from https://my.telegram.org |
| `MONGO_URI` | MongoDB connection string (Atlas SRV or local) |
| `AISHA_OPENROUTER_API_KEY` | OpenRouter API key (optional; offline sass answers if unset) |

## Config (non-secret — safe to set exactly)
| Key | Value | Description |
|---|---|---|
| `DB_NAME` | `aisha_bot` | MongoDB database name |
| `BOT_USERNAME` | `im_aishabot` | Bot Telegram handle |
| `OWNER_ID` | `6998484205` | Owner Telegram id |
| `OWNER_USERNAME` | `im_ntg` | Owner Telegram username |
| `AISHA_OWNER_NAME` | `ɴᴏᴛʜɪɴɢ` | Owner display name in chatbot persona |
| `AISHA_OWNER_USERNAME` | `im_ntg` | Owner handle in chatbot persona |
| `AISHA_OPENROUTER_MODEL` | `stealth/space-bunny-alpha` | Primary AI model |
| `AI_TIMEOUT` | `25` | AI provider timeout (seconds) |

## Notes
- Secrets are supplied through the host's environment, never committed to the repo.
- After saving env in the Render dashboard, the service redeploys automatically (`autoDeploy: true`).
