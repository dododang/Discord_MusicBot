import discord
from discord.ext import commands, tasks
from discord import ui
import asyncio
from yt_dlp import YoutubeDL
import os

# 명령어 버튼 UI 클래스
class CommandButtonView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for cmd, desc in COMMANDS_INFO.items():
            self.add_item(CommandButton(cmd, desc))

class CommandButton(ui.Button):
    def __init__(self, command: str, description: str):
        super().__init__(label=command, style=discord.ButtonStyle.primary)
        self.command = command
        self.description = description

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"**{self.command}**: {self.description}", ephemeral=True
        )


# YTDLSource 클래스 정의
class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'default_search': 'auto',
    }
    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        ytdl = YoutubeDL(cls.YTDL_OPTIONS)
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **cls.FFMPEG_OPTIONS), data=data)


# 버튼 인터페이스
class MusicControls(ui.View):
    def __init__(self, music_player):
        super().__init__(timeout=None)
        self.music_player = music_player

    @ui.button(label="정지", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.music_player.stop_music(interaction)

    @ui.button(label="일시정지", style=discord.ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.music_player.pause_music(interaction)

    @ui.button(label="재개", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.music_player.resume_music(interaction)

    @ui.button(label="스킵", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.music_player.skip_music(interaction)

    @ui.button(label="볼륨 조정", style=discord.ButtonStyle.success)
    async def volume_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            "볼륨을 0에서 100 사이로 입력해주세요.", ephemeral=True
        )
        try:
            message = await self.music_player.bot.wait_for(
                "message",
                check=lambda m: m.author == interaction.user and m.content.isdigit(),
                timeout=30,
            )
            volume = int(message.content)
            if 0 <= volume <= 100:
                await self.music_player.set_volume(volume / 100)
                await interaction.followup.send(f"볼륨이 {volume}%로 조정되었습니다.", ephemeral=True)
            else:
                await interaction.followup.send("0에서 100 사이의 값을 입력해주세요.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("시간 초과로 볼륨 입력이 취소되었습니다.", ephemeral=True)

    @ui.button(label="대기열 확인", style=discord.ButtonStyle.primary)
    async def queue_button(self, interaction: discord.Interaction, button: ui.Button):
        queue_list = self.music_player.get_queue_list()
        if queue_list:
            numbered_queue = [f"{i+1}. {title}" for i, title in enumerate(queue_list)]
            await interaction.response.send_message("대기열:\n" + "\n".join(numbered_queue), ephemeral=True)
        else:
            await interaction.response.send_message("현재 대기열에 음악이 없습니다.", ephemeral=True)

    @ui.button(label="🗑️ 대기열 삭제", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: ui.Button):
        queue_list = self.music_player.get_queue_list()
        if queue_list:
            await interaction.response.send_message(
                "대기열:\n" + "\n".join(queue_list) + "\n\n제거할 번호를 입력해주세요.", ephemeral=True
            )
        else:
            await interaction.response.send_message("현재 대기열에 음악이 없습니다.", ephemeral=True)
            return
        try:
            message = await self.music_player.bot.wait_for(
                "message",
                check=lambda m: m.author == interaction.user and m.content.isdigit(),
                timeout=30,
            )
            index = int(message.content) - 1
            removed = self.music_player.remove_from_queue(index)
            if removed:
                await interaction.followup.send(f"대기열에서 제거된 음악: **{removed}**", ephemeral=True)
            else:
                await interaction.followup.send("잘못된 인덱스입니다. 다시 확인해주세요.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("시간 초과로 작업이 취소되었습니다.", ephemeral=True)

    @ui.button(label="명령어 보기", style=discord.ButtonStyle.secondary)
    async def show_commands_button(self, interaction: discord.Interaction, button: ui.Button):
        commands_info = """
        아래는 사용 가능한 명령어 목록입니다.
        !play : 🎵 재생할 음악 URL 또는 제목을 입력하세요.
        !pause : ⏸ 현재 재생 중인 음악을 일시 정지합니다.
        !resume : ▶️ 일시 정지된 음악을 다시 재생합니다.
        !skip : ⏭ 현재 음악을 건너뛰고 다음 음악을 재생합니다.
        !stop : ⛔ 음악 재생을 완전히 중단합니다.
        !queue : 📜 대기열에 있는 음악 목록을 확인합니다.
        !volume : 🔊 볼륨을 0에서 100 사이로 조정합니다.
        !toggle_repeat : 🔄 반복재생 모드를 켜거나 끕니다.
        """
        # 명령어 정보를 DM 또는 임시 메시지로 전송
        await interaction.response.send_message(commands_info, ephemeral=True)


# MusicPlayer Cog 정의
class MusicPlayer(commands.Cog):
    def __init__(self, bot):   
        self.bot = bot
        self.queue = asyncio.Queue()
        self.now_playing = None
        self.message_with_buttons = None
        self.stop_flag = False  # 정지 상태 플래그
        self.repeat_mode = False  # 반복재생 플래그

    @commands.command()
    async def join(self, ctx):
        if not ctx.author.voice:
            await ctx.send("음성 채널에 먼저 접속해주세요.", delete_after=5)
            return
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        await ctx.message.delete()

    @commands.command()
    async def play(self, ctx, *, query):
        await ctx.message.delete()
        if not ctx.author.voice:
            await ctx.send("음성 채널에 먼저 접속해주세요.", delete_after=5)
            return
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()

        player = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
        await self.queue.put(player)

        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            await self.start_playing(ctx)
        else:
            await ctx.send(f"대기열에 추가됨: **{player.title}**", delete_after=3)
            
    @commands.command()
    async def toggle_repeat(self, ctx):
        """반복재생 모드를 토글합니다."""
        self.repeat_mode = not self.repeat_mode
        status = "활성화" if self.repeat_mode else "비활성화"
        await ctx.send(f"반복재생 모드가 {status}되었습니다.", delete_after=5)
            

    # start_playing 함수 수정
    async def start_playing(self, ctx):
        while not self.queue.empty():
            try:
                self.now_playing = await self.queue.get()

                # MusicControls 뷰 생성 시 명령어 보기 버튼 포함
                view = MusicControls(self)

                if self.message_with_buttons:
                    await self.message_with_buttons.edit(
                        content=f"재생 중: **{self.now_playing.title}**", 
                        view=view  # 수정된 view 적용
                    )
                else:
                    self.message_with_buttons = await ctx.send(
                        f"재생 중: **{self.now_playing.title}**", 
                        view=view  # 수정된 view 적용
                    )

                ctx.voice_client.play(
                    self.now_playing,
                    after=lambda e: self.bot.loop.create_task(self.play_next(ctx)),
                )
                while ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                    await asyncio.sleep(1)

                if self.stop_flag:
                    break
            except Exception as e:
                print(f"Error during playback: {e}")
                await self.play_next(ctx)


    async def play_next(self, ctx):
        if self.repeat_mode and self.now_playing:
            # 반복재생 모드 활성화 시 현재 곡을 대기열에 다시 추가
            await self.queue.put(self.now_playing)

        if not self.queue.empty() and not self.stop_flag:
            await self.start_playing(ctx)
        else:
            self.now_playing = None
            if self.message_with_buttons:
                await self.message_with_buttons.edit(
                    content="대기열이 비어 있습니다. 음악 재생을 종료합니다.", 
                    view=None
                )
                self.message_with_buttons = None

            await asyncio.sleep(30)
            if ctx.voice_client and not ctx.voice_client.is_playing():
                await self.cleanup_after_playback(ctx)

    async def cleanup_after_playback(self, ctx):
        if self.message_with_buttons:
            # 메시지 삭제 대신 상태만 업데이트
            await self.message_with_buttons.edit(
                content="음악 재생이 종료되었습니다.", 
                view=None
            )
            self.message_with_buttons = None

        if ctx.voice_client:
            await ctx.voice_client.disconnect()

    async def stop_music(self, interaction):
        self.queue = asyncio.Queue()  # 대기열 초기화
        self.stop_flag = True  # 정지 플래그 설정
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()  # 현재 재생 중인 음악 정지
            await interaction.guild.voice_client.disconnect()  # 음성 채널 연결 해제
        self.now_playing = None  # 현재 재생 중인 곡 초기화
        await interaction.response.send_message("음악 재생을 중단합니다.", ephemeral=True)

    async def pause_music(self, interaction):
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("음악이 일시 정지되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("재생 중인 음악이 없습니다.", ephemeral=True)

    async def resume_music(self, interaction):
        if interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("음악 재생을 재개합니다.", ephemeral=True)
        else:
            await interaction.response.send_message("일시 정지된 음악이 없습니다.", ephemeral=True)

    async def skip_music(self, interaction):
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("현재 음악을 스킵했습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("스킵할 음악이 없습니다.", ephemeral=True)

    async def set_volume(self, volume):
        if self.now_playing:
            self.now_playing.volume = volume

    def get_queue_list(self):
        # 현재 재생 중인 음악을 제외한 대기열 목록 반환
        return [item.title for item in self.queue._queue]
    
    
    def remove_from_queue(self, index):
        try:
            items = list(self.queue._queue)
            removed = items.pop(index)
            self.queue = asyncio.Queue()
            for item in items:
                self.queue.put_nowait(item)
            return removed.title if removed else None
        except IndexError:
            return None

# 봇 설정 및 실행
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")

    # 봇이 속한 모든 서버에서 채널 확인 및 생성
    for guild in bot.guilds:
        channel_name = "dongs-음악채널"
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)

        if not existing_channel:
            # 채널 생성
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }

            try:
                await guild.create_text_channel(channel_name, overwrites=overwrites)
                print(f"'{channel_name}' 채널이 생성되었습니다. ({guild.name})")
            except discord.Forbidden:
                print(f"'{channel_name}' 채널을 생성할 권한이 없습니다. ({guild.name})")
            except Exception as e:
                print(f"'{channel_name}' 채널 생성 중 오류 발생: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.guild.voice_client and len(member.guild.voice_client.channel.members) == 1:
        await asyncio.sleep(30)  # 30초 대기
        if len(member.guild.voice_client.channel.members) == 1:
            await member.guild.voice_client.disconnect()
    
async def main():
    async with bot:
        await bot.add_cog(MusicPlayer(bot))
        await bot.start("DISCORD_BOT_TOKEN")  # 환경 변수에서 불러온 토큰 사용

if __name__ == "__main__":
    asyncio.run(main())