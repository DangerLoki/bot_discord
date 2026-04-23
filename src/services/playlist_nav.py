"""Navegação sequencial e aleatória na playlist (pular / voltar)."""
import discord

from src.utils import embed_erro


class PlaylistNav:
    """Mixin: pular para o próximo vídeo e voltar ao anterior."""

    async def pular_video(self, ctx) -> None:
        playlist = self.repo.load()
        if not playlist:
            await ctx.send(embed=embed_erro('❌ Playlist vazia.'))
            return
        st = self.state
        if st.shuffle_mode:
            st.playlist_index = self.proximo_aleatorio(playlist)
            label = '🔀 Pulado (aleatório)'
        else:
            st.playlist_index = (st.playlist_index + 1) % len(playlist)
            tentativas = 0
            while tentativas < len(playlist) and playlist[st.playlist_index].get('tocado', False):
                st.playlist_index = (st.playlist_index + 1) % len(playlist)
                tentativas += 1
            label = '⏭️ Vídeo Pulado'
        video = playlist[st.playlist_index]
        embed = discord.Embed(
            title=label,
            description=f"Próximo: [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
            color=0x00FF00,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text='O vídeo foi pulado com sucesso.')
        await ctx.send(embed=embed)

    async def voltar_video(self, ctx) -> None:
        playlist = self.repo.load()
        if not playlist:
            await ctx.send(embed=embed_erro('❌ Playlist vazia.'))
            return
        st = self.state
        st.playlist_index = (st.playlist_index - 1) % len(playlist)
        tentativas = 0
        while tentativas < len(playlist) and playlist[st.playlist_index].get('tocado', False):
            st.playlist_index = (st.playlist_index - 1) % len(playlist)
            tentativas += 1
        video = playlist[st.playlist_index]
        embed = discord.Embed(
            title='⏮️ Vídeo Anterior',
            description=f"Anterior: [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
            color=0x00FF00,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text='Voltado ao vídeo anterior.')
        await ctx.send(embed=embed)
