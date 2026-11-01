#!/bin/bash
export $(grep DISCORD_BOT_TOKEN ~/.hermes/.env | xargs)
exec /Users/pirxcy/Services/AskCommand/.venv/bin/python /Users/pirxcy/Services/AskCommand/bot.py
