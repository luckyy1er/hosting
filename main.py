import discord
from discord.ext import commands
from discord import app_commands
import config
import io
import asyncio
from datetime import datetime

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

TICKET_TYPES = {
    "help": "A staff member will be with you shortly.",
    "lft": "Please link your tracker here.",
}

class TicketButtons(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="🎫 Help", style=discord.ButtonStyle.green, custom_id="ticket_help")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "help")

    @discord.ui.button(label="📢 LFT", style=discord.ButtonStyle.blurple, custom_id="ticket_lft")
    async def lft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "lft")

    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        category = interaction.guild.get_channel(config.CATEGORY_ID)
        channel = await interaction.guild.create_text_channel(
            name=f"{ticket_type}-ticket-{interaction.user.name}",
            category=category,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                interaction.guild.get_role(config.STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True),
            },
        )

        view = CloseButton()
        await channel.send(
            embed=discord.Embed(
                title=f"🎫 {ticket_type.capitalize()} Ticket",
                description=f"Ticket opened by {interaction.user.mention}\n\n{TICKET_TYPES[ticket_type]}",
                color=discord.Color.blue(),
            ),
            view=view
        )

        await interaction.response.send_message(
            f"Your ticket has been created: {channel.mention}", ephemeral=True
        )

class ConfirmClose(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=60)
        self.channel = channel

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing ticket and sending transcript in 5 seconds...", ephemeral=False)

        await asyncio.sleep(5)

        messages = []
        async for msg in self.channel.history(limit=1000, oldest_first=True):
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            author = msg.author
            content = msg.content.replace("\n", " ")
            line = f"[{timestamp}] {author}: {content}"

            if msg.attachments:
                attachment_links = " | ".join(att.url for att in msg.attachments)
                line += f" [Attachments: {attachment_links}]"

            messages.append(line)

        transcript_text = "\n".join(messages) or "No messages in this ticket."
        transcript_file = io.BytesIO(transcript_text.encode('utf-8'))
        transcript_file.seek(0)

        filename = f"transcript-{self.channel.name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.txt"

        transcript_channel = interaction.guild.get_channel(config.TRANSCRIPT_CHANNEL_ID)
        if transcript_channel:
            await transcript_channel.send(
                content=f"Transcript from ticket: `{self.channel.name}`",
                file=discord.File(fp=transcript_file, filename=filename)
            )
        else:
            await interaction.followup.send("⚠️ Transcript channel not found.", ephemeral=True)

        await self.channel.delete()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ticket close canceled.", ephemeral=True)
        self.stop()

class CloseButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = interaction.guild.get_role(config.STAFF_ROLE_ID)
        if staff_role not in interaction.user.roles:
            return await interaction.response.send_message(
                "You don’t have permission to close this ticket.", ephemeral=True
            )

        await interaction.response.send_message(
            "Are you sure you want to close this ticket?",
            view=ConfirmClose(interaction.channel),
        )


@tree.command(name="setup_tickets", description="Setup the ticket panel", guild=discord.Object(id=config.GUILD_ID))
async def setup_tickets(interaction: discord.Interaction):
    staff_role = interaction.guild.get_role(config.STAFF_ROLE_ID)
    if staff_role not in interaction.user.roles:
        return await interaction.response.send_message("You do not have permission to setup tickets.", ephemeral=True)

    embed = discord.Embed(
        title="Tickets",
        description="Click a button below to open a ticket.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=TicketButtons(interaction.user.id), ephemeral=False)


# ====== Funny ======

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    lowered = message.content.lower()

    # Only respond once per message
    if "shit" in lowered:
        await message.channel.send("💩")
    elif "sporty" in lowered:
        await message.channel.send(file=discord.File("deadfc.gif"))

    await bot.process_commands(message)

# ====== Staff-only ticket management commands ======

@tree.command(name="rename_ticket", description="Rename this ticket channel", guild=discord.Object(id=config.GUILD_ID))
@app_commands.describe(new_name="The new name for the ticket channel")
async def rename_ticket(interaction: discord.Interaction, new_name: str):
    staff_role = interaction.guild.get_role(config.STAFF_ROLE_ID)
    if staff_role not in interaction.user.roles:
        return await interaction.response.send_message("You do not have permission to rename tickets.", ephemeral=True)

    channel = interaction.channel
    try:
        await channel.edit(name=new_name)
        await interaction.response.send_message(f"Ticket renamed to `{new_name}`.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to rename ticket: {e}", ephemeral=True)

@tree.command(name="add_user", description="Add a user to this ticket", guild=discord.Object(id=config.GUILD_ID))
@app_commands.describe(user="The user to add to the ticket")
async def add_user(interaction: discord.Interaction, user: discord.Member):
    staff_role = interaction.guild.get_role(config.STAFF_ROLE_ID)
    if staff_role not in interaction.user.roles:
        return await interaction.response.send_message("You do not have permission to add users to tickets.", ephemeral=True)

    channel = interaction.channel
    try:
        await channel.set_permissions(user, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"Added {user.mention} to the ticket.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to add user: {e}", ephemeral=True)

@tree.command(name="remove_user", description="Remove a user from this ticket", guild=discord.Object(id=config.GUILD_ID))
@app_commands.describe(user="The user to remove from the ticket")
async def remove_user(interaction: discord.Interaction, user: discord.Member):
    staff_role = interaction.guild.get_role(config.STAFF_ROLE_ID)
    if staff_role not in interaction.user.roles:
        return await interaction.response.send_message("You do not have permission to remove users from tickets.", ephemeral=True)

    channel = interaction.channel
    try:
        await channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"Removed {user.mention} from the ticket.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to remove user: {e}", ephemeral=True)

# ====== Bot Ready Event ======

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))
    print(f"Logged in as {bot.user}")

bot.run(config.TOKEN)