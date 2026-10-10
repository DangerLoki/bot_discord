"""Métodos de adição de vídeos à playlist (URL e busca)."""
import asyncio
import time
import urllib.parse

import discord

from src.logger import get_logger
from src.services.playlist_add_bulk import _registro_base
from src.utils import embed_aviso, embed_carregando, embed_erro

logger = get_logger(__name__)


class PlaylistAdd:
    """Métodos de adição: URL direta e busca por texto."""

    # ------------------------------------------------------------------
    # Limpeza pós-confirmação
    # ------------------------------------------------------------------

    def _agendar_limpeza_confirmacao(self, ctx, msg, delay: float = 10.0) -> None:
        """Agenda em background a remoção da mensagem de confirmação de adição
        após `delay` segundos, e a atualização da mensagem de fila do painel.

        Roda como task separada para não bloquear o comando que adicionou o vídeo.
        """
        task = asyncio.create_task(self._limpar_confirmacao_apos_delay(ctx, msg, delay))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def _limpar_confirmacao_apos_delay(self, ctx, msg, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        player_svc = getattr(self, 'player_svc', None)
        if player_svc:
            playlist = self.repo.load(self.state.guild_id)
            await player_svc._atualizar_mensagem_playlist(ctx, playlist, self.state.playlist_index)

    # ------------------------------------------------------------------
    # Dispatch — decide o tipo de entrada (vídeo, playlist, Spotify, busca)
    # ------------------------------------------------------------------

    async def adicionar_entrada(self, ctx, entrada: str, bot) -> None:
        """Ponto único de entrada para o comando/botão de adicionar música.

        Detecta se `entrada` é uma URL do Spotify, uma playlist/mix do
        YouTube, uma URL de vídeo único ou um termo de busca, e delega
        para o método apropriado.
        """
        entrada = entrada.strip()
        if 'open.spotify.com' in entrada:
            logger.info(f'[ADD SPOTIFY] {entrada} por {ctx.author}')
            await self.adicionar_spotify(ctx, entrada, bot)
        elif entrada.startswith('http') and ('list=' in entrada or 'playlist' in entrada):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(entrada).query)
            list_id = params.get('list', [''])[0]
            if list_id.startswith('RD'):
                # YouTube Mix — adiciona só o vídeo do link, ignora a fila gerada
                video_id = params.get('v', [''])[0]
                url_limpa = f'https://www.youtube.com/watch?v={video_id}' if video_id else entrada
                logger.info(f'[ADD MIX→VIDEO] {url_limpa} por {ctx.author}')
                await ctx.send(
                    embed=discord.Embed(
                        description='ℹ️ Links de Mix do YouTube adicionam apenas o vídeo selecionado, não a fila inteira.',
                        color=0x5865F2,
                    )
                )
                await self.adicionar_por_url(ctx, url_limpa)
            else:
                logger.info(f'[ADD PLAYLIST] {entrada} por {ctx.author}')
                await self.adicionar_playlist_youtube(ctx, entrada)
        elif entrada.startswith('http'):
            logger.info(f'[ADD URL] {entrada} por {ctx.author}')
            await self.adicionar_por_url(ctx, entrada)
        else:
            logger.info(f'[ADD BUSCA] "{entrada}" por {ctx.author}')
            await self.adicionar_por_busca(ctx, entrada, bot)

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

        playlist = self.repo.load(self.state.guild_id)
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

        registro = _registro_base(
            video_id,
            titulo=info_video['titulo'] if info_video else None,
            duracao=info_video['duracao'] if info_video else None,
            duracao_formatada=info_video['duracao_formatada'] if info_video else '??:??',
            canal=info_video['canal'] if info_video else None,
            autor=str(ctx.author),
            extra={'posicao': len(playlist) + 1, 'url': url},
        )
        playlist, novos_indices = self.repo.add_unique(self.state.guild_id, [registro])
        if not novos_indices:
            await msg.edit(embed=embed_aviso('⚠️ Este vídeo já está na playlist.'))
            return
        novo_indice = novos_indices[0]
        registro = playlist[novo_indice]
        self._atualizar_shuffle_com_novo_video(novo_indice)

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
        self._agendar_limpeza_confirmacao(ctx, msg)

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
