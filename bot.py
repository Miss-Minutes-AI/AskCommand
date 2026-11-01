"""User-installable /ask command bridging Discord to Hermes.

Shows live tool-call progress while Hermes works, then replaces
the status message with only the final answer.
"""

import asyncio
import json
import os
import time

import discord
from discord import app_commands

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
ALLOWED = {384270258401181699}  # Kalib
HERMES = os.path.expanduser("~/.local/bin/hermes")
if not os.path.exists(HERMES):
    HERMES = "hermes"

TOOL_ICONS = {
    "web_search": "🔍",
    "web_extract": "🌐",
    "terminal": "💻",
    "read_file": "📄",
    "write_file": "✏️",
    "patch": "✏️",
    "search_files": "🗂️",
    "skill_view": "📚",
    "browser_exec": "🧭",
    "vision_analyze": "👁️",
}


def tool_line(name: str, inp) -> str:
    icon = TOOL_ICONS.get(name, "⚙️")
    detail = ""
    if isinstance(inp, dict):
        for key in ("query", "command", "path", "name", "pattern", "urls"):
            if inp.get(key):
                detail = str(inp[key])
                break
    detail = detail.replace("\n", " ")[:70]
    return f"{icon} `{name}` {detail}".rstrip()


intents = discord.Intents.none()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


async def run_hermes_live(question: str, edit) -> str:
    proc = await asyncio.create_subprocess_exec(
        HERMES, "chat", "-q", question, "-Q", "--format", "stream-json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    lines: list[str] = []
    final = ""
    last_edit = 0.0

    async def maybe_edit() -> None:
        nonlocal last_edit
        now = time.monotonic()
        if now - last_edit < 1.5:
            return
        last_edit = now
        body = "⏳ **Workin' on it...**\n" + "\n".join(lines[-8:] or ["Thinkin'..."])
        try:
            await edit(content=body[:2000])
        except discord.HTTPException:
            pass

    try:
        async with asyncio.timeout(600):
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type")
                if etype == "tool_use":
                    lines.append(tool_line(event.get("name", "?"), event.get("input")))
                    await maybe_edit()
                elif etype == "result":
                    final = (event.get("text") or "").strip()
    except TimeoutError:
        proc.kill()
        return "That one ran outta time, sugar. Try a simpler question."
    await proc.wait()
    return final or "No answer came back, sugar. Try again in a tick."


@tree.command(name="ask", description="Ask Miss Minutes anything, anywhere.")
@app_commands.describe(question="What do you want to know?")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ask(interaction: discord.Interaction, question: str) -> None:
    if interaction.user.id not in ALLOWED:
        await interaction.response.send_message(
            "Sorry sugar, this clock only ticks for one owner.", ephemeral=True
        )
        return
    await interaction.response.defer()
    msg = await interaction.followup.send("⏳ **Workin' on it...**", wait=True)
    answer = await run_hermes_live(question, msg.edit)
    header = f"> {question[:180]}\n"
    full = header + answer
    chunks = [full[i : i + 1990] for i in range(0, len(full), 1990)] or ["(empty)"]
    await msg.edit(content=chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@client.event
async def on_ready() -> None:
    # No tree.sync() here: a full sync REPLACES all global commands and
    # wipes the Hermes gateway's built-ins. /ask is registered once via
    # a single-command HTTP POST (register_ask.py), which is additive.
    print(f"Ready as {client.user}")


client.run(TOKEN)
