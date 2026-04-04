import os
import asyncio
import random

import discord
import yt_dlp

from src.logger import get_logger
from src.bot.utils import GeoBlockedError, _is_geo_blocked

logger = get_logger(__name__)


class PlayerMixin:
    """Métodos de reprodução de áudio em canal de voz."""

    # ------------------------------------------------------------------
    # Download e cache
    # ------------------------------------------------------------------

    async def baixar_audio(self, video_url: str, video_id: str) -> str | None:
        """Baixa o áudio para o cache e retorna o caminho do arquivo.
        Lança GeoBlockedError se o vídeo estiver bloqueado na região.
        """
        existente = list(self.cache_dir.glob(f'{video_id}.*'))
        if existente:
            logger.debug(f'[CACHE] usando arquivo em cache: {existente[0]}')
            return str(existente[0])

        destino = self.cache_dir / video_id
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(destino) + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '0',
            }],
        }
        if os.path.exists(self.cookies_file):
            opts['cookiefile'] = self.cookies_file
        if self.proxy:
            opts['proxy'] = self.proxy

        def _download():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
                resultado = list(self.cache_dir.glob(f'{video_id}.*'))
                return str(resultado[0]) if resultado else None
            except Exception as e:
                if _is_geo_blocked(str(e)):
                    raise GeoBlockedError(str(e))
                logger.error(f'[yt-dlp] erro ao baixar {video_url}: {e}')
                return None

        return await asyncio.to_thread(_download)

    def _limpar_cache(self, video_id: str) -> None:
        for f in self.cache_dir.glob(f'{video_id}.*'):
            try:
                f.unlink()
                logger.debug(f'[CACHE] removido: {f}')
            except Exception as e:
                logger.warning(f'[CACHE] falha ao remover {f}: {e}')

    def _atualizar_shuffle_com_novo_video(self, novo_indice: int) -> None:
        """Atualiza a lista de shuffle inserindo o novo vídeo em posição aleatória."""
        if not self.shuffle_mode or not self.shuffle_playlist:
            return
        
        # Insere o novo vídeo em uma posição aleatória da lista shuffle
        # (como uma seed: mantém ordem relativa mas insere novos elementos aleatoriamente)
        posicao_aleatoria = random.randint(0, len(self.shuffle_playlist))
        self.shuffle_playlist.insert(posicao_aleatoria, novo_indice)
        
        logger.info(f'[SHUFFLE] Vídeo na posição {novo_indice} inserido na posição {posicao_aleatoria} da lista aleatória (ID: {self.shuffle_id})')

    # ------------------------------------------------------------------
    # Lógica de shuffle
    # ------------------------------------------------------------------

    def _proximo_aleatorio(self, playlist: list) -> int:
        """Retorna o próximo índice da lista aleatória gerada."""
        if not self.shuffle_playlist or self.shuffle_index >= len(self.shuffle_playlist):
            # Regenera lista se necessário
            nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
            if nao_tocados:
                random.shuffle(nao_tocados)
                self.shuffle_playlist = nao_tocados
                self.shuffle_index = 0
            else:
                # Se todos foram tocados, reinicia ciclo
                for v in playlist:
                    v['tocado'] = False
                self.salvar_playlist(playlist)
                indices = list(range(len(playlist)))
                random.shuffle(indices)
                self.shuffle_playlist = indices
                self.shuffle_index = 0

        if self.shuffle_playlist:
            index = self.shuffle_playlist[self.shuffle_index]
            self.shuffle_index += 1
            return index
        return self.playlist_index

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------

    async def tocar_atual(self, ctx):
        """Ponto de entrada público — garante execução exclusiva via lock."""
        if self._carregando.locked():
            return
        async with self._carregando:
            await self._tocar_atual_impl(ctx)

    async def _tocar_atual_impl(self, ctx):
        if not self.voice_client or not self.voice_client.is_connected():
            await ctx.send('❌ Não estou em nenhum canal de voz!')
            return

        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.is_playing_voice = False
            self.voice_client.stop()

        while True:
            playlist = self.carregar_playlist()
            if not playlist:
                await ctx.send('❌ Playlist vazia. Adicione vídeos com `&add`.')
                return

            if self.playlist_index >= len(playlist):
                self.playlist_index = 0

            video = playlist[self.playlist_index]
            total = len(playlist)
            titulo = video.get('titulo', 'Desconhecido')
            video_url = video.get('embed_url', '')
            video_id = video.get('video_id', '')

            await ctx.send(f'🔄 Baixando áudio de **{titulo}**...')

            playlist[self.playlist_index]['tocado'] = True
            # Se está em modo shuffle, salva o shuffle_id e posicao_shuffle
            if self.shuffle_mode and self.shuffle_id:
                posicao_shuffle = self.shuffle_index + 1  # Posição atual no shuffle
                playlist[self.playlist_index]['shuffle_id'] = self.shuffle_id
                playlist[self.playlist_index]['posicao_shuffle'] = posicao_shuffle
            self.salvar_playlist(playlist)

            try:
                audio_path = await self.baixar_audio(video_url, video_id)
            except GeoBlockedError:
                await ctx.send(f'🌍 **{titulo}** está bloqueado na sua região e foi removido da playlist.')
                playlist = self.carregar_playlist()
                playlist = [v for v in playlist if v.get('video_id') != video_id]
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
                self.salvar_playlist(playlist)
                if not playlist:
                    await ctx.send('📋 Playlist vazia após remoção.')
                    return
                self.playlist_index = self.playlist_index % len(playlist)
                continue

            if not audio_path:
                await ctx.send(f'❌ Não consegui baixar o áudio de **{titulo}**. Pulando...')
                self.playlist_index = (self.playlist_index + 1) % len(playlist)
                # Pula músicas que já foram tocadas
                tentativas = 0
                while tentativas < len(playlist) and playlist[self.playlist_index].get('tocado', False):
                    self.playlist_index = (self.playlist_index + 1) % len(playlist)
                    tentativas += 1
                continue
            break

        try:
            source = discord.FFmpegPCMAudio(audio_path)
            source = discord.PCMVolumeTransformer(source, volume=self.voice_volume)
        except Exception as e:
            await ctx.send(f'❌ Erro ao criar stream de áudio: {e}')
            return

        self.is_playing_voice = True
        video_id_atual = video.get('video_id', '')

        def after_playing(error):
            if error:
                logger.error(f'Erro no player: {error}')
            self._limpar_cache(video_id_atual)
            if self.is_playing_voice and self.voice_client and self.voice_client.is_connected():
                asyncio.run_coroutine_threadsafe(
                    self._auto_next(ctx), self.voice_bot.loop
                )

        self.voice_client.play(source, after=after_playing)

        embed = discord.Embed(
            title='🔊 Tocando na Call',
            description=f"**[{titulo}]({video_url})**",
            color=0x1DB954,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
        embed.add_field(name='Posição', value=f"{self.playlist_index + 1}/{total}", inline=True)
        embed.add_field(name='Volume', value=f'{int(self.voice_volume * 100)}%', inline=True)
        await ctx.send(embed=embed)
        logger.info(f'[VOZ] Tocando: {titulo}')

    async def _auto_next(self, ctx):
        """Chamado automaticamente ao terminar uma música."""
        if not self.is_playing_voice:
            return

        playlist = self.carregar_playlist()
        if not playlist:
            self.is_playing_voice = False
            await ctx.send('📋 Playlist terminou!')
            return

        if self.shuffle_mode:
            self.playlist_index = self._proximo_aleatorio(playlist)
        else:
            self.playlist_index += 1
            if self.playlist_index >= len(playlist):
                self.playlist_index = 0
                self.is_playing_voice = False
                await ctx.send('📋 Playlist terminou! Use `&tocar` para recomeçar.')
                return
            
            # Verifica se a próxima música já foi tocada e pula para a próxima não tocada
            while self.playlist_index < len(playlist) and playlist[self.playlist_index].get('tocado', False):
                self.playlist_index += 1
            
            # Se chegou ao final, playlist terminou
            if self.playlist_index >= len(playlist):
                self.playlist_index = 0
                self.is_playing_voice = False
                await ctx.send('📋 Playlist terminou! Use `&tocar` para recomeçar.')
                return

        await self.tocar_atual(ctx)
