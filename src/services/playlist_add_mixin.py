"""Mixin: métodos de adição de vídeos à playlist."""
import asyncio
import time
from datetime import datetime

import discord

from src.logger import get_logger
from src.utils import embed_carregando, embed_erro, embed_aviso

logger = get_logger(__name__)


class PlaylistAddMixin:
    """Mixin com todos os métodos de adição: URL, busca, Spotify e playlist YT."""

    # ------------------------------------------------------------------
    # Adição por URL direta
    # ------------------------------------------------------------------

    async def adicionar_por_url(self, ctx, url: str, msg=None) -> None:
        from src.utils import extrair_video_id
        t0 = time.perf_counter()
        video_id = extrair_video_id(url)
        if not video_id:
            _send = msg.edit if msg else ctx.send
            await _send(embed=embed_erro('❌ URL inválida. Forneça uma URL válida do YouTube.'))
            return

        embed_url = f'https://www.youtube.com/watch?v={video_id}'
        thumbnail_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'

        playlist = self.repo.load()
        if any(item['video_id'] == video_id for item in playlist):
            _send = msg.edit if msg else ctx.send
            await _send(embed=embed_aviso('⚠️ Este vídeo já está na playlist.'))
            return

        if msg is None:
            msg = await ctx.send(embed=embed_carregando('🔍 Obtendo informações do vídeo...'))
        else:
            try:
                await msg.clear_reactions()
            except Exception:
                pass
            await msg.edit(embed=embed_carregando('🔍 Obtendo informações do vídeo...'))

        info_video = await self.yt.obter_info_video(url)
        if info_video and info_video.get('geo_blocked'):
            await msg.edit(
                embed=embed_erro('🌍 Este vídeo está bloqueado na sua região e não pode ser adicionado.')
            )
            return
        if info_video and info_video.get('is_live'):
            await msg.edit(
                embed=embed_erro(
                    '🔴 **Lives não são suportadas.**\n'
                    'Não é possível baixar transmissões ao vivo. Adicione um vídeo gravado.'
                )
            )
            return

        registro = {
            'video_id': video_id,
            'titulo': info_video['titulo'] if info_video else None,
            'duracao': info_video['duracao'] if info_video else None,
            'duracao_formatada': info_video['duracao_formatada'] if info_video else None,
            'canal': info_video['canal'] if info_video else None,
            'embed_url': embed_url,
            'thumbnail_url': thumbnail_url,
            'adicionado_por': str(ctx.author),
            'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'url': url,
            'posicao': len(playlist) + 1,
            'tocado': False,
        }
        playlist.append(registro)
        self.repo.save(playlist)
        self._atualizar_shuffle_com_novo_video(len(playlist) - 1)

        elapsed = time.perf_counter() - t0
        logger.info(
            f'[PERF][ADD_URL] "{registro["titulo"]}" ({video_id}) '
            f'por {ctx.author} — pos {registro["posicao"]} — tempo total={elapsed:.2f}s'
        )

        embed = discord.Embed(
            title=info_video['titulo'] if info_video else 'Vídeo Adicionado à Playlist',
            color=0x00FF00,
            url=embed_url,
        )
        embed.set_thumbnail(url=thumbnail_url)
        embed.add_field(name='Adicionado por', value=str(ctx.author), inline=True)
        if info_video:
            embed.add_field(name='Canal', value=info_video['canal'], inline=True)
            embed.add_field(name='Duração', value=info_video['duracao_formatada'], inline=True)
            embed.add_field(name='Visualizações', value=f"{info_video['views']:,}", inline=True)
            embed.add_field(name='Posição na Playlist', value=str(registro['posicao']), inline=True)
        embed.set_footer(text='Vídeo adicionado com sucesso! ✅')
        await msg.edit(embed=embed)

    # ------------------------------------------------------------------
    # Adição por busca
    # ------------------------------------------------------------------

    async def adicionar_por_busca(self, ctx, termo: str, bot) -> None:
        t0 = time.perf_counter()
        msg = await ctx.send(embed=embed_carregando(f'🔍 Buscando vídeos para **"{termo}"**...'))
        resultados = await self.yt.buscar_videos(termo)
        logger.debug(
            f'[PERF][ADD_BUSCA] busca concluída em {time.perf_counter()-t0:.2f}s para "{termo}"'
        )

        if not resultados:
            await msg.edit(embed=embed_erro('❌ Nenhum vídeo encontrado para o termo de busca.'))
            return

        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        descricao = ''
        for i, video in enumerate(resultados):
            descricao += (
                f"{emojis[i]} **{video['titulo']}**\n"
                f"Canal: {video['canal']}\nDuração: {video['duracao_formatada']}\n\n"
            )
        embed = discord.Embed(
            title='Selecione um vídeo para adicionar à playlist',
            description=descricao,
            color=0x00FF00,
        )
        await msg.edit(embed=embed)
        for emoji in emojis[: len(resultados)]:
            await msg.add_reaction(emoji)

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and reaction.emoji in emojis
            )

        try:
            reaction, _ = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=embed_aviso('⏰ Tempo esgotado. Por favor, tente novamente.'))
            return

        indice = emojis.index(reaction.emoji)
        video = resultados[indice]
        await self.adicionar_por_url(
            ctx, f"https://www.youtube.com/watch?v={video['video_id']}", msg=msg
        )

    # ------------------------------------------------------------------
    # Adição via Spotify
    # ------------------------------------------------------------------

    async def adicionar_spotify(self, ctx, url: str, bot) -> None:
        if not self.spotify.client_id or not self.spotify.client_secret:
            await ctx.send(embed=embed_erro(
                '❌ Spotify não configurado.\n'
                'Adicione `spotify_client_id` e `spotify_client_secret` ao `config.env`.\n'
                'Crie suas credenciais em: <https://developer.spotify.com/dashboard>'
            ))
            return

        tipo, spotify_id = self.spotify.extrair_tipo_id(url)
        if not tipo:
            await ctx.send(
                embed=embed_erro('❌ URL do Spotify inválida. Formatos aceitos: track, álbum ou playlist.')
            )
            return

        if tipo == 'track':
            await self._adicionar_spotify_track(ctx, spotify_id)
        elif tipo == 'album':
            msg = await ctx.send(embed=embed_carregando('🎵 Consultando álbum no Spotify...'))
            nome, artista, tracks = await self.spotify.obter_tracks_album(spotify_id)
            if not tracks:
                await msg.edit(embed=embed_erro('❌ Não foi possível obter as faixas do álbum.'))
                return
            titulo_label = f'💿 Álbum: {nome}' + (f' — {artista}' if artista else '')
            await self._adicionar_spotify_coletivo(ctx, titulo_label, tracks, url, msg=msg)
        elif tipo == 'playlist':
            msg = await ctx.send(embed=embed_carregando('🎵 Consultando playlist no Spotify...'))
            nome, tracks = await self.spotify.obter_tracks_playlist(spotify_id)
            if not tracks:
                await msg.edit(embed=embed_erro('❌ Não foi possível obter as faixas da playlist.'))
                return
            await self._adicionar_spotify_coletivo(ctx, f'🎶 Playlist: {nome}', tracks, url, msg=msg)
        else:
            await ctx.send(embed=embed_erro('❌ Tipo de URL do Spotify não suportado.'))

    async def _adicionar_spotify_track(self, ctx, track_id: str) -> None:
        msg = await ctx.send(embed=embed_carregando('🎵 Consultando faixa no Spotify...'))
        info = await self.spotify.obter_track(track_id)
        if not info:
            await msg.edit(embed=embed_erro('❌ Não foi possível obter informações da faixa no Spotify.'))
            return
        termo = f"{info['artista']} {info['titulo']}"
        await msg.edit(embed=embed_carregando(f'🔍 Buscando no YouTube: **{termo}**...'))
        resultados = await self.yt.buscar_videos(termo, max_resultados=1)
        if not resultados:
            await msg.edit(embed=embed_erro(f'❌ Não foi possível encontrar **{termo}** no YouTube.'))
            return
        video = resultados[0]
        await msg.delete()
        await self.adicionar_por_url(ctx, f"https://www.youtube.com/watch?v={video['video_id']}")

    async def _adicionar_spotify_coletivo(
        self, ctx, titulo_label: str, tracks: list, spotify_url: str, msg=None
    ) -> None:
        total = len(tracks)
        texto_inicial = f'{titulo_label}\n📋 {total} faixa(s) encontrada(s). Buscando no YouTube...'
        if msg is None:
            msg = await ctx.send(embed=embed_carregando(texto_inicial))
        else:
            await msg.edit(embed=embed_carregando(texto_inicial))

        adicionados = 0
        falhas = 0
        playlist = self.repo.load()
        ids_existentes = {v['video_id'] for v in playlist}
        novos_indices = []

        for i, track in enumerate(tracks, 1):
            termo = f"{track['artista']} {track['titulo']}"
            try:
                resultados = await self.yt.buscar_videos(termo, max_resultados=1)
                if not resultados:
                    falhas += 1
                    continue
                video = resultados[0]
                vid_id = video['video_id']
                if vid_id in ids_existentes:
                    continue
                embed_url = f'https://www.youtube.com/watch?v={vid_id}'
                playlist.append({
                    'video_id': vid_id,
                    'titulo': video.get('titulo', track['titulo']),
                    'duracao': track.get('duracao'),
                    'duracao_formatada': video.get('duracao_formatada', '??:??'),
                    'canal': video.get('canal', track.get('artista', 'Desconhecido')),
                    'embed_url': embed_url,
                    'thumbnail_url': f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg',
                    'adicionado_por': str(ctx.author),
                    'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'url': embed_url,
                    'posicao': len(playlist) + 1,
                    'tocado': False,
                    'fonte': 'spotify',
                    'spotify_titulo_original': track['titulo'],
                })
                novos_indices.append(len(playlist) - 1)
                ids_existentes.add(vid_id)
                adicionados += 1
                if i % 10 == 0 or i == total:
                    await msg.edit(
                        embed=embed_carregando(
                            f'{titulo_label}\n'
                            f'🔄 Progresso: {i}/{total} — '
                            f'✅ {adicionados} adicionadas, ❌ {falhas} não encontradas'
                        )
                    )
            except Exception as e:
                logger.error(f'[SPOTIFY] Erro ao adicionar faixa "{termo}": {e}')
                falhas += 1

        self.repo.save(playlist)
        for indice in novos_indices:
            self._atualizar_shuffle_com_novo_video(indice)

        embed = discord.Embed(title=titulo_label, color=0x1DB954, url=spotify_url)
        embed.add_field(name='✅ Adicionadas', value=str(adicionados), inline=True)
        embed.add_field(name='❌ Não encontradas', value=str(falhas), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author} · via Spotify → YouTube')
        await msg.edit(embed=embed)

    # ------------------------------------------------------------------
    # Adição de playlist do YouTube
    # ------------------------------------------------------------------

    async def adicionar_playlist_youtube(self, ctx, url: str) -> None:
        msg = await ctx.send(embed=embed_carregando('🔍 Carregando playlist, aguarde...'))
        titulo_pl, videos, is_mix = await self.yt.obter_videos_playlist(url)
        if not videos:
            await msg.edit(
                content='❌ Nenhum vídeo encontrado na playlist. Verifique se a URL é válida e se é pública.'
            )
            return
        playlist = self.repo.load()
        ids_existentes = {v['video_id'] for v in playlist}
        tipo_icone = '🎲' if is_mix else '📋'
        await msg.edit(
            embed=embed_carregando(
                f'{tipo_icone} **{titulo_pl}** — {len(videos)} vídeos encontrados. Adicionando...'
            )
        )
        adicionados = 0
        duplicados = 0
        novos_indices = []
        for video in videos:
            if video['video_id'] in ids_existentes:
                duplicados += 1
                continue
            playlist.append({
                'video_id': video['video_id'],
                'titulo': video['titulo'],
                'duracao': video['duracao'],
                'duracao_formatada': video['duracao_formatada'],
                'canal': video['canal'],
                'embed_url': video['embed_url'],
                'thumbnail_url': video['thumbnail_url'],
                'adicionado_por': str(ctx.author),
                'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'url': video['embed_url'],
                'posicao': len(playlist) + 1,
                'tocado': False,
            })
            novos_indices.append(len(playlist) - 1)
            ids_existentes.add(video['video_id'])
            adicionados += 1
        self.repo.save(playlist)
        for indice in novos_indices:
            self._atualizar_shuffle_com_novo_video(indice)

        embed = discord.Embed(title=f'{tipo_icone} {titulo_pl}', color=0x00FF00, url=url)
        embed.add_field(name='✅ Adicionados', value=str(adicionados), inline=True)
        embed.add_field(name='⚠️ Já na fila', value=str(duplicados), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author}')
        await msg.edit(embed=embed)
