# music_view.py - Interactive Discord Buttons, Modals, and Pagination Views
import discord
import math
from loguru import logger

class PlayModal(discord.ui.Modal, title="🔗 Paste Link or Search"):
    query = discord.ui.TextInput(
        label="URL or Search Query",
        placeholder="YouTube, Spotify, SoundCloud link or search text...",
        required=True,
        max_length=250
    )

    def __init__(self, bot, player):
        super().__init__()
        self.bot = bot
        self.player = player

    async def on_submit(self, interaction: discord.Interaction):
        # Delegate play logic to the music cog
        music_cog = self.bot.get_cog("Music")
        if not music_cog:
            return await interaction.response.send_message("❌ Music system offline.", ephemeral=True)
        
        # music_cog._play_internal will defer the interaction and run track extraction
        await music_cog._play_internal(interaction, self.query.value)


class QueuePaginationView(discord.ui.View):
    def __init__(self, tracks, current_track, author):
        super().__init__(timeout=60.0)
        self.tracks = tracks
        self.current_track = current_track
        self.author = author
        self.current_page = 0
        self.per_page = 10
        self.max_pages = math.ceil(len(tracks) / self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.max_pages - 1

    def make_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📋 Current Playlist Queue",
            color=discord.Color.blurple()
        )
        
        if self.current_track:
            duration_str = ""
            if self.current_track.get('duration'):
                m, s = divmod(self.current_track.get('duration'), 60)
                duration_str = f" ({m}:{s:02d})"
            
            req_name = self.current_track.get('requester_name', 'Unknown')
            embed.add_field(
                name="🎶 Now Playing",
                value=f"**{self.current_track.get('title')}**{duration_str}\nRequested by: {req_name}",
                inline=False
            )

        if not self.tracks:
            embed.description = "The queue is empty."
            return embed

        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_tracks = self.tracks[start_idx:end_idx]

        q_list = ""
        for idx, track in enumerate(page_tracks, start=start_idx + 1):
            dur = ""
            if track.get('duration'):
                m, s = divmod(track.get('duration'), 60)
                dur = f" `[{m}:{s:02d}]`"
            q_list += f"`{idx}.` **{track.get('title')}**{dur}\n"

        embed.add_field(
            name="Up Next",
            value=q_list or "No more tracks in queue.",
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {max(1, self.max_pages)} • Total Tracks: {len(self.tracks)}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the user who opened the queue can navigate it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)


class MusicControlView(discord.ui.View):
    def __init__(self, bot, player):
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot
        self.player = player
        self.sync_button_states()

    def sync_button_states(self):
        """Enable/disable and color buttons based on current player state."""
        # 1. Loop Mode Status Styling
        loop_mode = self.player.queue.loop_mode
        if loop_mode == 1:
            self.loop_btn.style = discord.ButtonStyle.primary
            self.loop_btn.label = "🔂 Loop: Track"
        elif loop_mode == 2:
            self.loop_btn.style = discord.ButtonStyle.success
            self.loop_btn.label = "🔁 Loop: Queue"
        else:
            self.loop_btn.style = discord.ButtonStyle.secondary
            self.loop_btn.label = "🔁 Loop: Off"

        # 2. Play/Pause state label toggles
        vc = self.player.guild.voice_client
        if vc and vc.is_paused():
            self.play_pause_btn.label = "▶️ Resume"
            self.play_pause_btn.style = discord.ButtonStyle.success
        else:
            self.play_pause_btn.label = "⏸️ Pause"
            self.play_pause_btn.style = discord.ButtonStyle.secondary

        # 3. Disable control checks for empty conditions
        has_history = len(self.player.queue.history) > 0
        has_upcoming = len(self.player.queue.tracks) > 0
        has_active = self.player.current_track is not None

        self.prev_btn.disabled = not has_history
        self.skip_btn.disabled = not has_upcoming and not (loop_mode > 0 and has_active)
        self.shuffle_btn.disabled = len(self.player.queue.tracks) <= 1
        
        # Disable play/pause and loop when nothing is playing
        self.play_pause_btn.disabled = not has_active
        self.loop_btn.disabled = not has_active
        
        # Disable stop/leave button if not connected to voice client
        self.stop_btn.disabled = vc is None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verify voice channel state requirements."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ You must be in a voice channel first.", ephemeral=True)
            return False
            
        custom_id = interaction.data.get("custom_id")
        vc = interaction.guild.voice_client

        if custom_id == "play_url":
            if vc and interaction.user.voice.channel != vc.channel:
                await interaction.response.send_message("❌ You must be in the same voice channel as the bot to control it.", ephemeral=True)
                return False
            return True

        if not vc:
            await interaction.response.send_message("❌ Bot is not active in voice.", ephemeral=True)
            return False

        if interaction.user.voice.channel != vc.channel:
            await interaction.response.send_message("❌ You must be in the same voice channel as the bot to control it.", ephemeral=True)
            return False
            
        return True

    @discord.ui.button(label="⏮ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        success = self.player.skip_backward()
        if success:
            await self.player.update_now_playing_message()
            # Send ephemeral confirmation
            await interaction.followup.send("⏮ Replaying the previous track.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No previous track history exists.", ephemeral=True)

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.secondary, row=0)
    async def play_pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = self.player.guild.voice_client
        if vc:
            if vc.is_playing():
                vc.pause()
                self.player.paused_at = self.player.bot.loop.time() if hasattr(self.player.bot.loop, 'time') else None
                await interaction.followup.send("⏸️ Paused playback.", ephemeral=True)
            elif vc.is_paused():
                vc.resume()
                if getattr(self.player, 'paused_at', None) and getattr(self.player, 'play_start_time', None):
                    now = self.player.bot.loop.time()
                    self.player.play_start_time += (now - self.player.paused_at)
                    self.player.paused_at = None
                await interaction.followup.send("▶️ Resumed playback.", ephemeral=True)
        await self.player.update_now_playing_message()

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = self.player.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop() # triggers toggle_next in playback_loop
            await interaction.followup.send("⏭️ Skipped current track.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
        # Update is driven automatically by player.playback_loop next event, 
        # but edit buttons immediately just in case
        self.sync_button_states()

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger, row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        music_cog = self.bot.get_cog("Music")
        
        # Clear queue and stop playback
        self.player.queue.clear()
        vc = self.player.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
            
        if music_cog and self.player.guild.id in music_cog.players:
            self.player.destroy()
            del music_cog.players[self.player.guild.id]
            
        await interaction.followup.send("⏹ Stopped playback, cleared the queue, and disconnected.", ephemeral=True)

    @discord.ui.button(label="🔀 Shuffle", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.player.queue.shuffle()
        await self.player.update_now_playing_message()
        await interaction.followup.send("🔀 Shuffled the upcoming tracks queue.", ephemeral=True)

    @discord.ui.button(label="🔁 Loop: Off", style=discord.ButtonStyle.secondary, row=1)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.player.queue.loop_mode = (self.player.queue.loop_mode + 1) % 3
        await self.player.update_now_playing_message()
        modes = ["Loop disabled.", "Now repeating the current track.", "Now repeating the queue."]
        await interaction.followup.send(f"🔁 {modes[self.player.queue.loop_mode]}", ephemeral=True)

    @discord.ui.button(label="🔗 Play Link", style=discord.ButtonStyle.primary, row=1, custom_id="play_url")
    async def add_music_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Interaction cannot be deferred before showing modal!
        modal = PlayModal(self.bot, self.player)
        await interaction.response.send_modal(modal)
