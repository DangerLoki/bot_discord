import os
import json
import asyncio
import random
from datetime import datetime

import discord

from src.logger import get_logger
from src.bot.utils import extrair_video_id, GeoBlockedError, extrair_spotify_tipo_id, embed_carregando, embed_erro, embed_aviso

logger = get_logger(__name__)


class PlaylistMixin:
    """Métodos de gerenciamento da playlist (CRUD + adição)."""

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def carregar_playlist(self) -> list:
        if not os.path.exists(self.json_playlist):
            return []
        try:
            with open(self.json_playlist, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                return json.loads(conteudo) if conteudo else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def salvar_playlist(self, playlist: list) -> None:
        os.makedirs(os.path.dirname(self.json_playlist), exist_ok=True)
        with open(self.json_playlist, 'w', encoding='utf-8') as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Adição de vídeos
    # ------------------------------------------------------------------

    async def adicionar_por_url(self, ctx, url: str, msg=None):
        video_id = extrair_video_id(url)
        if not video_id:
            _send = msg.edit if msg else ctx.send
            await _send(embed=embed_erro('❌ URL inválida. Por favor, forneça uma URL válida do YouTube.'))
            return

        embed_url = f'https://www.youtube.com/watch?v={video_id}'
        thumbnail_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'

        playlist = self.carregar_playlist()
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
        info_video = await self.obter_info_video(url)

        if info_video and info_video.get('geo_blocked'):
            await msg.edit(embed=embed_erro('🌍 Este vídeo está bloqueado na sua região e não pode ser adicionado.'))
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
        self.salvar_playlist(playlist)
        
        # Atualiza lista de shuffle se estiver ativa
        novo_indice = len(playlist) - 1
        self._atualizar_shuffle_com_novo_video(novo_indice)
        
        logger.info(f'[ADD] "{registro["titulo"]}" ({video_id}) por {ctx.author} — pos {registro["posicao"]}')

        embed = discord.Embed(
            title=info_video['titulo'] if info_video else 'Vídeo Adicionado à Playlist',
            color=0x00FF00,
            url=embed_url,
        )
        embed.set_thumbnail(url=thumbnail_url)
        embed.add_field(name="Adicionado por", value=str(ctx.author), inline=True)
        if info_video:
            embed.add_field(name="Canal", value=info_video['canal'], inline=True)
            embed.add_field(name="Duração", value=info_video['duracao_formatada'], inline=True)
            embed.add_field(name="Visualizações", value=f"{info_video['views']:,}", inline=True)
            embed.add_field(name="Posição na Playlist", value=str(registro['posicao']), inline=True)
        embed.set_footer(text="Vídeo adicionado com sucesso! ✅")
        await msg.edit(embed=embed)

    async def adicionar_por_busca(self, ctx, termo: str, bot):
        msg = await ctx.send(embed=embed_carregando(f'🔍 Buscando vídeos para **"{termo}"**...'))
        resultados = await self.buscar_videos_youtube(termo)

        if not resultados:
            await msg.edit(embed=embed_erro('❌ Nenhum vídeo encontrado para o termo de busca fornecido.'))
            return

        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        descricao = ''
        for i, video in enumerate(resultados):
            descricao += (
                f"{emojis[i]} **{video['titulo']}**\n"
                f"Canal: {video['canal']}\nDuração: {video['duracao_formatada']}\n\n"
            )

        embed = discord.Embed(
            title="Selecione um vídeo para adicionar à playlist",
            description=descricao,
            color=0x00FF00,
        )
        await msg.edit(embed=embed)
        for emoji in emojis[:len(resultados)]:
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
        await self.adicionar_por_url(ctx, f"https://www.youtube.com/watch?v={video['video_id']}", msg=msg)

    # ------------------------------------------------------------------
    # Adição via Spotify
    # ------------------------------------------------------------------

    async def adicionar_spotify(self, ctx, url: str, bot):
        """Ponto de entrada para URLs do Spotify (track, álbum ou playlist)."""
        if not getattr(self, 'spotify_client_id', None) or not getattr(self, 'spotify_client_secret', None):
            await ctx.send(embed=embed_erro(
                '❌ Spotify não configurado.\n'
                'Adicione `spotify_client_id` e `spotify_client_secret` ao `config.env`.\n'
                'Crie suas credenciais em: <https://developer.spotify.com/dashboard>'
            ))
            return

        tipo, spotify_id = extrair_spotify_tipo_id(url)
        if not tipo:
            await ctx.send(embed=embed_erro('❌ URL do Spotify inválida. Formatos aceitos: track, álbum ou playlist.'))
            return

        if tipo == 'track':
            await self._adicionar_spotify_track(ctx, spotify_id)
        elif tipo == 'album':
            msg = await ctx.send(embed=embed_carregando('🎵 Consultando álbum no Spotify...'))
            nome, artista, tracks = await self.obter_tracks_spotify_album(spotify_id)
            if not tracks:
                await msg.edit(embed=embed_erro('❌ Não foi possível obter as faixas do álbum.'))
                return
            titulo_label = f'💿 Álbum: {nome}' + (f' — {artista}' if artista else '')
            await self._adicionar_spotify_coletivo(ctx, titulo_label, tracks, url, msg=msg)
        elif tipo == 'playlist':
            msg = await ctx.send(embed=embed_carregando('🎵 Consultando playlist no Spotify...'))
            nome, tracks = await self.obter_tracks_spotify_playlist(spotify_id)
            if not tracks:
                await msg.edit(embed=embed_erro('❌ Não foi possível obter as faixas da playlist.'))
                return
            await self._adicionar_spotify_coletivo(ctx, f'🎶 Playlist: {nome}', tracks, url, msg=msg)
        else:
            await ctx.send(embed=embed_erro('❌ Tipo de URL do Spotify não suportado.'))

    async def _adicionar_spotify_track(self, ctx, track_id: str):
        """Busca uma faixa do Spotify no YouTube e adiciona à playlist."""
        msg = await ctx.send(embed=embed_carregando('🎵 Consultando faixa no Spotify...'))
        info = await self.obter_info_spotify_track(track_id)
        if not info:
            await msg.edit(embed=embed_erro('❌ Não foi possível obter informações da faixa no Spotify.'))
            return

        termo = f"{info['artista']} {info['titulo']}"
        await msg.edit(embed=embed_carregando(f'🔍 Buscando no YouTube: **{termo}**...'))
        resultados = await self.buscar_videos_youtube(termo, max_resultados=1)

        if not resultados:
            await msg.edit(embed=embed_erro(f'❌ Não foi possível encontrar **{termo}** no YouTube.'))
            return

        video = resultados[0]
        await msg.delete()
        await self.adicionar_por_url(ctx, f"https://www.youtube.com/watch?v={video['video_id']}")

    async def _adicionar_spotify_coletivo(
        self, ctx, titulo_label: str, tracks: list, spotify_url: str, msg=None
    ):
        """Adiciona várias faixas do Spotify pesquisando cada uma no YouTube."""
        total = len(tracks)
        texto_inicial = f'{titulo_label}\n📋 {total} faixa(s) encontrada(s). Buscando no YouTube...'
        if msg is None:
            msg = await ctx.send(embed=embed_carregando(texto_inicial))
        else:
            await msg.edit(embed=embed_carregando(texto_inicial))

        adicionados = 0
        falhas = 0
        playlist = self.carregar_playlist()
        ids_existentes = {v['video_id'] for v in playlist}
        novos_indices = []

        for i, track in enumerate(tracks, 1):
            termo = f"{track['artista']} {track['titulo']}"
            try:
                resultados = await self.buscar_videos_youtube(termo, max_resultados=1)
                if not resultados:
                    falhas += 1
                    continue

                video = resultados[0]
                vid_id = video['video_id']

                if vid_id in ids_existentes:
                    continue  # já está na fila, não duplica

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

                # Atualiza mensagem de progresso a cada 10 faixas
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

        self.salvar_playlist(playlist)
        for indice in novos_indices:
            self._atualizar_shuffle_com_novo_video(indice)

        embed = discord.Embed(title=titulo_label, color=0x1DB954, url=spotify_url)
        embed.add_field(name='✅ Adicionadas', value=str(adicionados), inline=True)
        embed.add_field(name='❌ Não encontradas', value=str(falhas), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author} · via Spotify → YouTube')
        await msg.edit(embed=embed)

    async def adicionar_playlist(self, ctx, url: str):
        """Adiciona todos os vídeos de uma playlist do YouTube à fila."""
        msg = await ctx.send(embed=embed_carregando('🔍 Carregando playlist, aguarde...'))
        titulo_pl, videos, is_mix = await self.obter_videos_playlist(url)

        if not videos:
            await msg.edit(
                content='❌ Nenhum vídeo encontrado na playlist. Verifique se a URL é válida e se a playlist é pública.'
            )
            return

        playlist = self.carregar_playlist()
        ids_existentes = {v['video_id'] for v in playlist}
        tipo_icone = '🎲' if is_mix else '📋'
        await msg.edit(embed=embed_carregando(f'{tipo_icone} **{titulo_pl}** — {len(videos)} vídeos encontrados. Adicionando...'))

        adicionados = 0
        duplicados = 0
        novos_indices = []  # Rastreia índices dos novos vídeos adicionados
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
            novos_indices.append(len(playlist) - 1)  # Índice do vídeo recém-adicionado
            ids_existentes.add(video['video_id'])
            adicionados += 1

        self.salvar_playlist(playlist)
        
        # Atualiza lista de shuffle para cada novo vídeo adicionado
        for indice in novos_indices:
            self._atualizar_shuffle_com_novo_video(indice)

        embed = discord.Embed(title=f'{tipo_icone} {titulo_pl}', color=0x00FF00, url=url)
        embed.add_field(name='✅ Adicionados', value=str(adicionados), inline=True)
        embed.add_field(name='⚠️ Já na fila', value=str(duplicados), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author}')
        await msg.edit(embed=embed)

    # ------------------------------------------------------------------
    # Remoção / reordenação
    # ------------------------------------------------------------------

    async def remover_video(self, ctx, entrada: str = None):
        if not entrada:
            await ctx.send(
                "❌ Use: `&remove <posição>` ou `&remove <video_id>`\n"
                "Exemplos: `&remove 5` | `&remove dQw4w9WgXcQ`"
            )
            return

        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("⚠️ A playlist está vazia.")
            return

        # Se shuffle estiver ativo, trabalha com posições da lista shuffle
        if self.shuffle_mode and self.shuffle_playlist:
            if entrada.isdigit():
                shuffle_pos = int(entrada) - 1
                if shuffle_pos < 0 or shuffle_pos >= len(self.shuffle_playlist):
                    await ctx.send(f"❌ Posição inválida. A lista aleatória tem {len(self.shuffle_playlist)} vídeos.")
                    return
                # Converte posição da lista shuffle para índice na playlist base
                index = self.shuffle_playlist[shuffle_pos]
                video = playlist[index]
                posicao_label = entrada
            else:
                video_id = extrair_video_id(entrada) or entrada.strip()
                video = next((v for v in playlist if v.get('video_id') == video_id), None)
                if not video:
                    await ctx.send(f"❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.")
                    return
                # Encontra posição na lista shuffle
                index = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)
                shuffle_pos = next((i for i, pos in enumerate(self.shuffle_playlist) if pos == index), None)
                posicao_label = str(shuffle_pos + 1) if shuffle_pos is not None else "?"
        else:
            # Modo normal
            if entrada.isdigit():
                index = int(entrada) - 1
                if index < 0 or index >= len(playlist):
                    await ctx.send(f"❌ Posição inválida. A playlist tem {len(playlist)} vídeos.")
                    return
                video = playlist[index]
                posicao_label = entrada
            else:
                video_id = extrair_video_id(entrada) or entrada.strip()
                video = next((v for v in playlist if v.get('video_id') == video_id), None)
                if not video:
                    await ctx.send(f"❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.")
                    return
                posicao_label = str(video.get('posicao', '?'))
                index = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)

        video_id = video.get('video_id')
        titulo = video.get('titulo', 'Desconhecido')
        
        removendo_atual = index == self.playlist_index
        playlist.pop(index)
        
        # Atualiza posições na playlist base
        for i, v in enumerate(playlist):
            v['posicao'] = i + 1
        
        # Atualiza lista shuffle se estiver ativa
        if self.shuffle_mode and self.shuffle_playlist:
            # Remove o índice da lista shuffle e ajusta índices maiores
            self.shuffle_playlist = [pos if pos < index else pos - 1 for pos in self.shuffle_playlist if pos != index]
        
        self.salvar_playlist(playlist)

        if len(playlist) == 0:
            self.playlist_index = 0
            if self.shuffle_mode:
                self.shuffle_playlist = []
        elif index < self.playlist_index:
            self.playlist_index -= 1
        elif removendo_atual and self.playlist_index >= len(playlist):
            self.playlist_index = 0

        embed = discord.Embed(title="🗑️ Vídeo Removido!", description=f"**{titulo}**", color=0xFF0000)
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name="Posição", value=posicao_label, inline=True)
        embed.add_field(name="ID", value=f"`{video_id}`", inline=True)
        embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
        if removendo_atual and playlist:
            embed.add_field(
                name="▶️ Tocando agora",
                value=playlist[self.playlist_index].get('titulo', 'Desconhecido'),
                inline=False,
            )
        embed.set_footer(text=f"Removido por {ctx.author}")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Busca por título (auxiliar para promover_video / remover_video)
    # ------------------------------------------------------------------

    async def _resolver_entrada_por_titulo(self, ctx, bot, playlist: list, entrada: str):
        """Tenta resolver uma entrada de texto como título (parcial/case-insensitive).

        Retorna (index_video, video, msg) em caso de sucesso, onde msg é a
        mensagem interativa que pode ser editada pelo chamador para o resultado
        final (None se não houve interação). Retorna (None, None, None) se o
        usuário cancelar / não for encontrado.
        """
        entrada_lower = entrada.lower()

        # Coleta candidatos: (índice_na_playlist, video)
        candidatos = []
        for i, v in enumerate(playlist):
            titulo = v.get('titulo', '')
            if entrada_lower == titulo.lower():
                # Match exato (case-insensitive) → usa imediatamente, sem interação
                return i, v, None
            if entrada_lower in titulo.lower():
                candidatos.append((i, v))

        if not candidatos:
            return None, None, None

        if len(candidatos) == 1:
            # Um único resultado parcial → pede confirmação com reações
            idx, video = candidatos[0]
            titulo_video = video.get('titulo', 'Desconhecido')
            embed = discord.Embed(
                title="🔍 Confirmar Promoção",
                description=(
                    f"Você quis dizer:\n\n"
                    f"**{titulo_video}**\n\n"
                    f"Reaja com ✅ para confirmar ou ❌ para cancelar."
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

        # Múltiplos resultados → lista para o usuário escolher com reações
        max_mostrar = min(len(candidatos), 9)
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
        descricao = "Encontrei mais de um resultado. Qual você quer promover?\n\n"
        for i in range(max_mostrar):
            _, video = candidatos[i]
            descricao += f"{emojis[i]} **{video.get('titulo', 'Desconhecido')}**\n"
        descricao += "\nReaja com o número da opção desejada."

        embed = discord.Embed(
            title="🔍 Múltiplos Resultados",
            description=descricao,
            color=0x5865F2,
        )
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

    async def promover_video(self, ctx, entrada: str = None, bot=None):
        if not entrada:
            await ctx.send(
                "❌ Use: `&promover <posição>`, `&promover <video_id>` ou `&promover <nome da música>`\n"
                "Exemplos: `&promover 6` | `&promover dQw4w9WgXcQ` | `&promover never gonna`"
            )
            return

        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("⚠️ A playlist está vazia.")
            return

        # --- Auxiliar: resolve entrada não-numérica por video_id ou título ---
        async def _resolver_nao_numerico(entrada_str: str):
            video_id = extrair_video_id(entrada_str)
            if video_id:
                v = next((x for x in playlist if x.get('video_id') == video_id), None)
                if not v:
                    await ctx.send(f"❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.")
                    return None, None, None
                i = next(j for j, x in enumerate(playlist) if x.get('video_id') == video_id)
                return i, v, None

            # Tenta match exato por video_id (sem extrair URL)
            vid = entrada_str.strip()
            v = next((x for x in playlist if x.get('video_id') == vid), None)
            if v:
                i = next(j for j, x in enumerate(playlist) if x.get('video_id') == vid)
                return i, v, None

            # Fallback: busca por título (parcial, case-insensitive)
            if bot is None:
                await ctx.send(f"❌ Não encontrei nenhum vídeo com ID `{vid}` na playlist.")
                return None, None, None

            i, v, msg = await self._resolver_entrada_por_titulo(ctx, bot, playlist, entrada_str)
            if v is None and msg is None:
                # Só envia mensagem de erro se _resolver não enviou nenhuma
                entrada_lower_check = entrada_str.lower()
                achou_candidato = any(entrada_lower_check in x.get('titulo', '').lower() for x in playlist)
                if not achou_candidato:
                    await ctx.send(f"❌ Nenhuma música encontrada com o nome **\"{entrada_str}\"** na playlist.")
            return i, v, msg

        confirm_msg = None  # mensagem interativa reutilizável para o resultado final

        # Se shuffle estiver ativo, trabalha com posições da lista shuffle
        if self.shuffle_mode and self.shuffle_playlist:
            if entrada.isdigit():
                shuffle_pos = int(entrada) - 1
                if shuffle_pos < 0 or shuffle_pos >= len(self.shuffle_playlist):
                    await ctx.send(f"❌ Posição inválida. A lista aleatória tem {len(self.shuffle_playlist)} vídeos.")
                    return
                index_video = self.shuffle_playlist[shuffle_pos]
                video = playlist[index_video]
            else:
                index_video, video, confirm_msg = await _resolver_nao_numerico(entrada)
                if video is None:
                    return
        else:
            # Modo normal
            if entrada.isdigit():
                index_video = int(entrada) - 1
                if index_video < 0 or index_video >= len(playlist):
                    await ctx.send(f"❌ Posição inválida. A playlist tem {len(playlist)} vídeos.")
                    return
                video = playlist[index_video]
            else:
                index_video, video, confirm_msg = await _resolver_nao_numerico(entrada)
                if video is None:
                    return

        video_id = video.get('video_id')
        if index_video == self.playlist_index:
            await ctx.send("⚠️ Este vídeo já está tocando.")
            return

        # Calcula próxima posição baseada no modo atual
        if self.shuffle_mode and self.shuffle_playlist:
            # No modo shuffle, promove para a próxima posição na lista shuffle
            current_shuffle_pos = next((i for i, pos in enumerate(self.shuffle_playlist) if pos == index_video), None)
            if current_shuffle_pos is None:
                await ctx.send("❌ Erro interno: vídeo não encontrado na lista shuffle.")
                return
            
            next_shuffle_pos = (self.shuffle_index + 1) % len(self.shuffle_playlist)
            
            if current_shuffle_pos == next_shuffle_pos:
                nova_pos = next_shuffle_pos + 1
            else:
                # Move na lista shuffle
                self.shuffle_playlist.pop(current_shuffle_pos)
                self.shuffle_playlist.insert(next_shuffle_pos, index_video)
                nova_pos = next_shuffle_pos + 1
        else:
            # Modo normal
            next_index = (self.playlist_index + 1) % len(playlist)

            if index_video == next_index:
                nova_pos = next_index + 1
            else:
                playlist.pop(index_video)
                if index_video < self.playlist_index:
                    self.playlist_index -= 1
                next_pos = self.playlist_index + 1
                playlist.insert(next_pos, video)
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
                nova_pos = next_pos + 1

        self.salvar_playlist(playlist)
        titulo_log = video.get('titulo', video_id)
        modo = "SHUFFLE" if self.shuffle_mode else "NORMAL"
        logger.info(f'[PROMOTE] {modo} {video_id} ("{titulo_log}") → posição {nova_pos}')
        
        embed = discord.Embed(
            title="⏭️ Vídeo Promovido!",
            description=f"**{video.get('titulo', video_id)}** será o próximo a tocar.",
            color=0xFECA57,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name="Nova Posição", value=str(nova_pos), inline=True)
        embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
        embed.set_footer(text=f"Promovido por {ctx.author}")
        if confirm_msg:
            await confirm_msg.edit(embed=embed)
        else:
            await ctx.send(embed=embed)

    async def limpar_playlist(self, ctx):
        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("⚠️ A playlist já está vazia.")
            return
        total = len(playlist)
        self.salvar_playlist([])
        self.playlist_index = 0
        logger.info(f'[CLEAR] Playlist limpa por {ctx.author}')
        embed = discord.Embed(
            title="🗑️ Playlist Limpa!",
            description=f"**{total}** vídeo(s) removido(s).",
            color=0xFF0000,
        )
        embed.set_footer(text=f"Limpa por {ctx.author}")
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Navegação de índice
    # ------------------------------------------------------------------

    async def pular_video(self, ctx):
        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send(embed=embed_erro('❌ Playlist vazia.'))
            return

        if self.shuffle_mode:
            self.playlist_index = self._proximo_aleatorio(playlist)
            label = '🔀 Pulado (aleatório)'
        else:
            self.playlist_index = (self.playlist_index + 1) % len(playlist)
            # Pula músicas que já foram tocadas
            tentativas = 0
            while tentativas < len(playlist) and playlist[self.playlist_index].get('tocado', False):
                self.playlist_index = (self.playlist_index + 1) % len(playlist)
                tentativas += 1
            label = '⏭️ Vídeo Pulado'

        video = playlist[self.playlist_index]
        embed = discord.Embed(
            title=label,
            description=f"Próximo: [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
            color=0x00FF00,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text='O vídeo foi pulado com sucesso.')
        await ctx.send(embed=embed)

    async def voltar_video(self, ctx):
        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send(embed=embed_erro('❌ Playlist vazia.'))
            return
        self.playlist_index = (self.playlist_index - 1) % len(playlist)
        # Pula músicas que já foram tocadas ao voltar
        tentativas = 0
        while tentativas < len(playlist) and playlist[self.playlist_index].get('tocado', False):
            self.playlist_index = (self.playlist_index - 1) % len(playlist)
            tentativas += 1
        video = playlist[self.playlist_index]
        embed = discord.Embed(
            title="⏮️ Vídeo Anterior",
            description=f"Anterior: [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
            color=0x00FF00,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text="Voltado ao vídeo anterior.")
        await ctx.send(embed=embed)
