"""Navegação sequencial e aleatória na playlist (pular / voltar)."""
import discord

from src.utils import embed_erro


class PlaylistNav:
    """Mixin: pular para o próximo vídeo e voltar ao anterior."""

    async def pular_video(self, ctx, *, announce: bool = True) -> None:
        playlist = self.repo.load(self.state.guild_id)
        if not playlist:
            await ctx.send(embed=embed_erro('❌ Playlist vazia.'))
            return
        st = self.state
        if 0 <= st.playlist_index < len(playlist):
            playlist[st.playlist_index]['tocado'] = True
            self.repo.save(self.state.guild_id, playlist)
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
        if announce:
            video = playlist[st.playlist_index]
            embed = discord.Embed(
                title=label,
                description=f"Próximo: [{video.get('titulo') or 'Desconhecido'}]({video.get('embed_url') or '#'})",
                color=0x00FF00,
            )
            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
            embed.set_footer(text='O vídeo foi pulado com sucesso.')
            await ctx.send(embed=embed)
        await self._atualizar_painel(ctx, player=False)

    async def voltar_video(self, ctx, *, announce: bool = True) -> None:
        playlist = self.repo.load(self.state.guild_id)
        if not playlist:
            await ctx.send(embed=embed_erro('❌ Playlist vazia.'))
            return
        st = self.state
        if st.shuffle_mode and st.shuffle_playlist:
            try:
                posicao_atual = st.shuffle_playlist.index(st.playlist_index)
            except ValueError:
                posicao_atual = max(0, st.shuffle_index - 1)
            posicao_anterior = (posicao_atual - 1) % len(st.shuffle_playlist)
            st.playlist_index = st.shuffle_playlist[posicao_anterior]
            st.shuffle_index = posicao_anterior + 1
        else:
            st.playlist_index = (st.playlist_index - 1) % len(playlist)
        # Ao voltar, reseta o flag tocado para permitir reprodução
        playlist[st.playlist_index]['tocado'] = False
        self.repo.save(self.state.guild_id, playlist)
        if not announce:
            await self._atualizar_painel(ctx, player=False)
            return
        video = playlist[st.playlist_index]
        embed = discord.Embed(
            title='⏮️ Vídeo Anterior',
            description=f"Anterior: [{video.get('titulo') or 'Desconhecido'}]({video.get('embed_url') or '#'})",
            color=0x00FF00,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text='Voltado ao vídeo anterior.')
        await ctx.send(embed=embed)
        await self._atualizar_painel(ctx, player=False)
