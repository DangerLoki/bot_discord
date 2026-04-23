"""Remoção, promoção, limpeza e navegação da playlist."""
import asyncio

import discord

from src.logger import get_logger
from src.utils import extrair_video_id, embed_aviso, embed_erro

logger = get_logger(__name__)


class PlaylistManage:
    """Remoção, promoção, limpeza e navegação de vídeos na fila."""

    # ------------------------------------------------------------------
    # Remoção
    # ------------------------------------------------------------------

    async def remover_video(self, ctx, entrada: str | None = None) -> None:
        if not entrada:
            await ctx.send(
                '❌ Use: `&remove <posição>` ou `&remove <video_id>`\n'
                'Exemplos: `&remove 5` | `&remove dQw4w9WgXcQ`'
            )
            return
        playlist = self.repo.load()
        if not playlist:
            await ctx.send('⚠️ A playlist está vazia.')
            return

        st = self.state
        if st.shuffle_mode and st.shuffle_playlist:
            if entrada.isdigit():
                shuffle_pos = int(entrada) - 1
                if shuffle_pos < 0 or shuffle_pos >= len(st.shuffle_playlist):
                    await ctx.send(f'❌ Posição inválida. A lista aleatória tem {len(st.shuffle_playlist)} vídeos.')
                    return
                index = st.shuffle_playlist[shuffle_pos]
                video = playlist[index]
                posicao_label = entrada
            else:
                video_id = extrair_video_id(entrada) or entrada.strip()
                video = next((v for v in playlist if v.get('video_id') == video_id), None)
                if not video:
                    await ctx.send(f'❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.')
                    return
                index = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)
                shuffle_pos = next(
                    (i for i, pos in enumerate(st.shuffle_playlist) if pos == index), None
                )
                posicao_label = str(shuffle_pos + 1) if shuffle_pos is not None else '?'
        else:
            if entrada.isdigit():
                index = int(entrada) - 1
                if index < 0 or index >= len(playlist):
                    await ctx.send(f'❌ Posição inválida. A playlist tem {len(playlist)} vídeos.')
                    return
                video = playlist[index]
                posicao_label = entrada
            else:
                video_id = extrair_video_id(entrada) or entrada.strip()
                video = next((v for v in playlist if v.get('video_id') == video_id), None)
                if not video:
                    await ctx.send(f'❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.')
                    return
                posicao_label = str(video.get('posicao', '?'))
                index = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)

        video_id = video.get('video_id')
        titulo = video.get('titulo', 'Desconhecido')
        removendo_atual = index == st.playlist_index

        playlist.pop(index)
        for i, v in enumerate(playlist):
            v['posicao'] = i + 1

        if st.shuffle_mode and st.shuffle_playlist:
            st.shuffle_playlist = [
                pos if pos < index else pos - 1
                for pos in st.shuffle_playlist
                if pos != index
            ]

        self.repo.save(playlist)

        if len(playlist) == 0:
            st.playlist_index = 0
            if st.shuffle_mode:
                st.shuffle_playlist = []
        elif index < st.playlist_index:
            st.playlist_index -= 1
        elif removendo_atual and st.playlist_index >= len(playlist):
            st.playlist_index = 0

        embed = discord.Embed(title='🗑️ Vídeo Removido!', description=f'**{titulo}**', color=0xFF0000)
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Posição', value=posicao_label, inline=True)
        embed.add_field(name='ID', value=f'`{video_id}`', inline=True)
        embed.add_field(name='Canal', value=video.get('canal', 'Desconhecido'), inline=True)
        if removendo_atual and playlist:
            embed.add_field(
                name='▶️ Tocando agora',
                value=playlist[st.playlist_index].get('titulo', 'Desconhecido'),
                inline=False,
            )
        embed.set_footer(text=f'Removido por {ctx.author}')
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Promoção
    # ------------------------------------------------------------------

    async def promover_video(self, ctx, entrada: str | None = None, bot=None) -> None:
        if not entrada:
            await ctx.send(
                '❌ Use: `&promover <posição>`, `&promover <video_id>` ou `&promover <nome>`\n'
                'Exemplos: `&promover 6` | `&promover dQw4w9WgXcQ` | `&promover never gonna`'
            )
            return
        playlist = self.repo.load()
        if not playlist:
            await ctx.send('⚠️ A playlist está vazia.')
            return

        st = self.state

        async def _resolver_nao_numerico(entrada_str):
            video_id = extrair_video_id(entrada_str)
            if video_id:
                v = next((x for x in playlist if x.get('video_id') == video_id), None)
                if not v:
                    await ctx.send(f'❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.')
                    return None, None, None
                i = next(j for j, x in enumerate(playlist) if x.get('video_id') == video_id)
                return i, v, None
            vid = entrada_str.strip()
            v = next((x for x in playlist if x.get('video_id') == vid), None)
            if v:
                i = next(j for j, x in enumerate(playlist) if x.get('video_id') == vid)
                return i, v, None
            if bot is None:
                await ctx.send(f'❌ Não encontrei nenhum vídeo com ID `{vid}` na playlist.')
                return None, None, None
            i, v, msg = await self._resolver_entrada_por_titulo(ctx, bot, playlist, entrada_str)
            if v is None and msg is None:
                entrada_lower = entrada_str.lower()
                if not any(entrada_lower in x.get('titulo', '').lower() for x in playlist):
                    await ctx.send(f'❌ Nenhuma música encontrada com o nome **"{entrada_str}"** na playlist.')
            return i, v, msg

        confirm_msg = None

        if st.shuffle_mode and st.shuffle_playlist:
            if entrada.isdigit():
                shuffle_pos = int(entrada) - 1
                if shuffle_pos < 0 or shuffle_pos >= len(st.shuffle_playlist):
                    await ctx.send(f'❌ Posição inválida. A lista aleatória tem {len(st.shuffle_playlist)} vídeos.')
                    return
                index_video = st.shuffle_playlist[shuffle_pos]
                video = playlist[index_video]
            else:
                index_video, video, confirm_msg = await _resolver_nao_numerico(entrada)
                if video is None:
                    return
        else:
            if entrada.isdigit():
                index_video = int(entrada) - 1
                if index_video < 0 or index_video >= len(playlist):
                    await ctx.send(f'❌ Posição inválida. A playlist tem {len(playlist)} vídeos.')
                    return
                video = playlist[index_video]
            else:
                index_video, video, confirm_msg = await _resolver_nao_numerico(entrada)
                if video is None:
                    return

        video_id = video.get('video_id')
        if index_video == st.playlist_index:
            await ctx.send('⚠️ Este vídeo já está tocando.')
            return

        if st.shuffle_mode and st.shuffle_playlist:
            current_shuffle_pos = next(
                (i for i, pos in enumerate(st.shuffle_playlist) if pos == index_video), None
            )
            if current_shuffle_pos is None:
                await ctx.send('❌ Erro interno: vídeo não encontrado na lista shuffle.')
                return
            next_shuffle_pos = (st.shuffle_index + 1) % len(st.shuffle_playlist)
            if current_shuffle_pos != next_shuffle_pos:
                st.shuffle_playlist.pop(current_shuffle_pos)
                st.shuffle_playlist.insert(next_shuffle_pos, index_video)
            nova_pos = next_shuffle_pos + 1
        else:
            next_index = (st.playlist_index + 1) % len(playlist)
            if index_video != next_index:
                playlist.pop(index_video)
                if index_video < st.playlist_index:
                    st.playlist_index -= 1
                next_pos = st.playlist_index + 1
                playlist.insert(next_pos, video)
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
                nova_pos = next_pos + 1
            else:
                nova_pos = next_index + 1
        self.repo.save(playlist)

        modo = 'SHUFFLE' if st.shuffle_mode else 'NORMAL'
        logger.info(f'[PROMOTE] {modo} {video_id} ("{video.get("titulo", video_id)}") → posição {nova_pos}')

        embed = discord.Embed(
            title='⏭️ Vídeo Promovido!',
            description=f'**{video.get("titulo", video_id)}** será o próximo a tocar.',
            color=0xFECA57,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Nova Posição', value=str(nova_pos), inline=True)
        embed.add_field(name='Canal', value=video.get('canal', 'Desconhecido'), inline=True)
        embed.set_footer(text=f'Promovido por {ctx.author}')
        if confirm_msg:
            await confirm_msg.edit(embed=embed)
        else:
            await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Limpeza
    # ------------------------------------------------------------------

    async def limpar_playlist(self, ctx) -> None:
        playlist = self.repo.load()
        if not playlist:
            await ctx.send('⚠️ A playlist já está vazia.')
            return
        total = len(playlist)
        self.repo.save([])
        self.state.playlist_index = 0
        logger.info(f'[CLEAR] Playlist limpa por {ctx.author}')
        embed = discord.Embed(
            title='🗑️ Playlist Limpa!',
            description=f'**{total}** vídeo(s) removido(s).',
            color=0xFF0000,
        )
        embed.set_footer(text=f'Limpa por {ctx.author}')
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Navegação (pular / voltar)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Resolução de entrada por título (auxiliar de promover_video)
    # ------------------------------------------------------------------

    async def _resolver_entrada_por_titulo(self, ctx, bot, playlist: list, entrada: str):
        entrada_lower = entrada.lower()
        candidatos = []
        for i, v in enumerate(playlist):
            titulo = v.get('titulo', '')
            if entrada_lower == titulo.lower():
                return i, v, None
            if entrada_lower in titulo.lower():
                candidatos.append((i, v))

        if not candidatos:
            return None, None, None

        if len(candidatos) == 1:
            idx, video = candidatos[0]
            embed = discord.Embed(
                title='🔍 Confirmar Promoção',
                description=(
                    f'Você quis dizer:\n\n**{video.get("titulo", "Desconhecido")}**\n\n'
                    f'Reaja com ✅ para confirmar ou ❌ para cancelar.'
                ),
                color=0x5865F2,
            )
            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
            msg = await ctx.send(embed=embed)
            await msg.add_reaction('✅')
            await msg.add_reaction('❌')

            def check_reacao(reaction, user):
                return (
                    user == ctx.author
                    and reaction.message.id == msg.id
                    and str(reaction.emoji) in ('✅', '❌')
                )

            try:
                reaction, _ = await bot.wait_for('reaction_add', check=check_reacao, timeout=30.0)
            except asyncio.TimeoutError:
                await msg.edit(embed=embed_aviso('⏰ Tempo esgotado. Promoção cancelada.'))
                return None, None, None
            if str(reaction.emoji) == '✅':
                return idx, video, msg
            else:
                await msg.edit(embed=embed_aviso('❌ Promoção cancelada.'))
                return None, None, None

        max_mostrar = min(len(candidatos), 9)
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
        descricao = 'Encontrei mais de um resultado. Qual você quer promover?\n\n'
        for i in range(max_mostrar):
            _, video = candidatos[i]
            descricao += f"{emojis[i]} **{video.get('titulo', 'Desconhecido')}**\n"
        descricao += '\nReaja com o número da opção desejada.'
        embed = discord.Embed(title='🔍 Múltiplos Resultados', description=descricao, color=0x5865F2)
        msg = await ctx.send(embed=embed)
        for emoji in emojis[:max_mostrar]:
            await msg.add_reaction(emoji)

        def check_multi(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and reaction.emoji in emojis[:max_mostrar]
            )

        try:
            reaction, _ = await bot.wait_for('reaction_add', check=check_multi, timeout=30.0)
        except asyncio.TimeoutError:
            await msg.edit(embed=embed_aviso('⏰ Tempo esgotado. Promoção cancelada.'))
            return None, None, None

        escolha = emojis.index(reaction.emoji)
        idx, video = candidatos[escolha]
        return idx, video, msg
