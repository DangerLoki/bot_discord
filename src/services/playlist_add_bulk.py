"""Adições em lote: Spotify (track/álbum/playlist) e playlist do YouTube."""
from datetime import datetime

import discord

from src.logger import get_logger
from src.utils import embed_carregando, embed_erro

logger = get_logger(__name__)


def _registro_base(video_id: str, titulo: str, duracao, duracao_formatada: str,
                   canal: str, autor: str, extra: dict | None = None) -> dict:
    """Monta o dicionário padrão de um item da playlist."""
    registro = {
        'video_id': video_id,
        'titulo': titulo,
        'duracao': duracao,
        'duracao_formatada': duracao_formatada,
        'canal': canal,
        'embed_url': f'https://www.youtube.com/watch?v={video_id}',
        'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
        'adicionado_por': autor,
        'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'url': f'https://www.youtube.com/watch?v={video_id}',
        'tocado': False,
    }
    if extra:
        registro.update(extra)
    return registro


class PlaylistAddBulk:
    """Mixin: adição em lote via Spotify e playlist do YouTube."""

    # ------------------------------------------------------------------
    # Spotify
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

        adicionados, falhas = 0, 0
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
                reg = _registro_base(
                    vid_id,
                    titulo=video.get('titulo', track['titulo']),
                    duracao=track.get('duracao'),
                    duracao_formatada=video.get('duracao_formatada', '??:??'),
                    canal=video.get('canal', track.get('artista', 'Desconhecido')),
                    autor=str(ctx.author),
                    extra={
                        'posicao': len(playlist) + 1,
                        'fonte': 'spotify',
                        'spotify_titulo_original': track['titulo'],
                    },
                )
                playlist.append(reg)
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
        for idx in novos_indices:
            self._atualizar_shuffle_com_novo_video(idx)

        embed = discord.Embed(title=titulo_label, color=0x1DB954, url=spotify_url)
        embed.add_field(name='✅ Adicionadas', value=str(adicionados), inline=True)
        embed.add_field(name='❌ Não encontradas', value=str(falhas), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author} · via Spotify → YouTube')
        await msg.edit(embed=embed)

    # ------------------------------------------------------------------
    # Playlist do YouTube
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

        adicionados, duplicados = 0, 0
        novos_indices = []
        for video in videos:
            if video['video_id'] in ids_existentes:
                duplicados += 1
                continue
            reg = _registro_base(
                video['video_id'],
                titulo=video['titulo'],
                duracao=video['duracao'],
                duracao_formatada=video['duracao_formatada'],
                canal=video['canal'],
                autor=str(ctx.author),
                extra={'posicao': len(playlist) + 1},
            )
            playlist.append(reg)
            novos_indices.append(len(playlist) - 1)
            ids_existentes.add(video['video_id'])
            adicionados += 1

        self.repo.save(playlist)
        for idx in novos_indices:
            self._atualizar_shuffle_com_novo_video(idx)

        embed = discord.Embed(title=f'{tipo_icone} {titulo_pl}', color=0x00FF00, url=url)
        embed.add_field(name='✅ Adicionados', value=str(adicionados), inline=True)
        embed.add_field(name='⚠️ Já na fila', value=str(duplicados), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author}')
        await msg.edit(embed=embed)
