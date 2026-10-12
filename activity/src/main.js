import { DiscordSDK, patchUrlMappings } from '@discord/embedded-app-sdk';
import './styles.css';

const elements = {
  syncPill: document.querySelector('#sync-pill'),
  syncLabel: document.querySelector('#sync-label'),
  videoFrame: document.querySelector('#video-frame'),
  player: document.querySelector('#youtube-player'),
  empty: document.querySelector('#empty-state'),
  emptyTitle: document.querySelector('#empty-title'),
  emptyCopy: document.querySelector('#empty-copy'),
  title: document.querySelector('#track-title'),
  channel: document.querySelector('#track-channel'),
  progress: document.querySelector('#progress-bar'),
  elapsed: document.querySelector('#elapsed'),
  duration: document.querySelector('#duration'),
  queue: document.querySelector('#queue-list'),
  mode: document.querySelector('#mode-badge'),
  resync: document.querySelector('#resync-button'),
  youtube: document.querySelector('#youtube-button'),
  fullscreen: document.querySelector('#fullscreen-button'),
  notice: document.querySelector('#notice'),
};

const runtime = {
  embedded: new URLSearchParams(window.location.search).has('frame_id'),
  discord: null,
  guildId: new URLSearchParams(window.location.search).get('guild_id'),
  config: null,
  snapshot: null,
  iframe: null,
  playerReady: false,
  playerPosition: null,
  playerReadyTimer: null,
  videoId: null,
  playbackStatus: null,
  fetchedAt: 0,
  lastHardSyncAt: 0,
  timer: null,
};

function apiPath(path) {
  return `${runtime.embedded ? '/.proxy' : ''}${path}`;
}

function youtubeEmbedUrl(videoId, startAt) {
  const params = new URLSearchParams({
    autoplay: '1',
    mute: '1',
    controls: '1',
    fs: '0',
    playsinline: '1',
    enablejsapi: '1',
    rel: '0',
    start: String(Math.max(0, Math.floor(startAt))),
    origin: window.location.origin,
  });
  return `https://www.youtube.com/embed/${encodeURIComponent(videoId)}?${params}`;
}

function playerCommand(func, args = []) {
  if (!runtime.iframe?.contentWindow) return;
  runtime.iframe.contentWindow.postMessage(
    JSON.stringify({ event: 'command', func, args }),
    '*',
  );
}

function thumbnailUrl(track) {
  if (track.video_id) {
    return `https://img.youtube.com/vi/${encodeURIComponent(track.video_id)}/hqdefault.jpg`;
  }
  return track.thumbnail_url;
}

function desiredPosition() {
  const playback = runtime.snapshot?.playback;
  if (!playback) return 0;
  const extra = playback.status === 'playing'
    ? Math.max(0, (Date.now() - runtime.fetchedAt) / 1000)
    : 0;
  return playback.position_seconds + extra;
}

function hardSync() {
  if (!runtime.videoId || !runtime.playerReady) return;
  const position = desiredPosition();
  playerCommand('seekTo', [position, true]);
  playerCommand(runtime.snapshot.playback.status === 'playing' ? 'playVideo' : 'pauseVideo');
  runtime.playerPosition = position;
  runtime.lastHardSyncAt = Date.now();
  flashNotice('Clipe sincronizado com o áudio da call.');
}

function showPlayerError(code = null) {
  const blocked = [101, 150].includes(Number(code));
  const unidentified = Number(code) === 153;
  elements.empty.hidden = false;
  elements.emptyTitle.textContent = blocked
    ? 'Este clipe não permite incorporação'
    : 'O YouTube não carregou o clipe';
  elements.emptyCopy.textContent = unidentified
    ? 'O YouTube recusou a identificação da Activity. Use o botão YouTube para abrir o clipe.'
    : 'Use o botão YouTube abaixo ou aguarde a próxima faixa.';
  setSyncState('error', code ? `Erro do YouTube ${code}` : 'Player indisponível');
}

function mountVideo(videoId, position, status) {
  window.clearTimeout(runtime.playerReadyTimer);
  elements.player.replaceChildren();
  const iframe = document.createElement('iframe');
  iframe.title = 'Clipe sincronizado da música atual';
  iframe.src = youtubeEmbedUrl(videoId, position);
  iframe.allow = 'autoplay; encrypted-media; picture-in-picture';
  iframe.referrerPolicy = 'strict-origin-when-cross-origin';
  iframe.addEventListener('load', () => {
    const announcePlayer = () => {
      iframe.contentWindow?.postMessage(JSON.stringify({ event: 'listening' }), '*');
    };
    announcePlayer();
    window.setTimeout(announcePlayer, 500);
  });
  elements.player.append(iframe);
  runtime.iframe = iframe;
  runtime.playerReady = false;
  runtime.playerPosition = null;
  runtime.videoId = videoId;
  runtime.playbackStatus = status;
  runtime.lastHardSyncAt = Date.now();
  elements.empty.hidden = true;
  elements.resync.disabled = false;
  elements.youtube.disabled = false;
  runtime.playerReadyTimer = window.setTimeout(() => {
    if (runtime.videoId === videoId && !runtime.playerReady) showPlayerError();
  }, 10000);
}

function unmountVideo(title, copy) {
  elements.player.replaceChildren();
  runtime.iframe = null;
  runtime.playerReady = false;
  runtime.playerPosition = null;
  window.clearTimeout(runtime.playerReadyTimer);
  runtime.videoId = null;
  runtime.playbackStatus = null;
  elements.empty.hidden = false;
  elements.emptyTitle.textContent = title;
  elements.emptyCopy.textContent = copy;
  elements.resync.disabled = true;
  elements.youtube.disabled = true;
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return hours
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function setSyncState(kind, label) {
  elements.syncPill.className = `sync-pill ${kind}`;
  elements.syncLabel.textContent = label;
}

function flashNotice(message) {
  elements.notice.textContent = message;
  elements.notice.classList.add('visible');
  window.clearTimeout(flashNotice.timeout);
  flashNotice.timeout = window.setTimeout(() => elements.notice.classList.remove('visible'), 2600);
}

function nativeFullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function isVideoFullscreen() {
  return nativeFullscreenElement() === elements.videoFrame
    || elements.videoFrame.classList.contains('fullscreen-fallback');
}

function updateFullscreenButton() {
  const active = isVideoFullscreen();
  elements.fullscreen.setAttribute('aria-pressed', String(active));
  elements.fullscreen.setAttribute(
    'aria-label',
    active ? 'Sair da tela cheia' : 'Colocar o vídeo em tela cheia',
  );
  elements.fullscreen.title = active ? 'Sair da tela cheia' : 'Tela cheia';
}

function enterFallbackFullscreen() {
  elements.videoFrame.classList.add('fullscreen-fallback');
  document.body.classList.add('video-fullscreen-fallback');
  updateFullscreenButton();
}

function exitFallbackFullscreen() {
  elements.videoFrame.classList.remove('fullscreen-fallback');
  document.body.classList.remove('video-fullscreen-fallback');
  updateFullscreenButton();
}

async function toggleVideoFullscreen() {
  if (elements.videoFrame.classList.contains('fullscreen-fallback')) {
    exitFallbackFullscreen();
    return;
  }

  if (nativeFullscreenElement() === elements.videoFrame) {
    const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
    if (exitFullscreen) await exitFullscreen.call(document);
    return;
  }

  const requestFullscreen = elements.videoFrame.requestFullscreen
    || elements.videoFrame.webkitRequestFullscreen;
  if (!requestFullscreen) {
    enterFallbackFullscreen();
    return;
  }

  try {
    await requestFullscreen.call(elements.videoFrame);
  } catch (error) {
    console.warn('Tela cheia nativa indisponível; usando modo expandido.', error);
    enterFallbackFullscreen();
  }
}

function renderQueue(queue) {
  elements.queue.replaceChildren();
  if (!queue.length) {
    const empty = document.createElement('li');
    empty.className = 'queue-empty';
    empty.textContent = 'Nenhuma próxima faixa na fila.';
    elements.queue.append(empty);
    return;
  }
  queue.forEach((track, index) => {
    const item = document.createElement('li');
    item.className = 'queue-item';

    const position = document.createElement('span');
    position.className = 'queue-position';
    position.textContent = String(index + 1).padStart(2, '0');

    const image = document.createElement('img');
    image.src = thumbnailUrl(track);
    image.alt = '';
    image.loading = 'lazy';

    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = track.title;
    const channel = document.createElement('span');
    channel.textContent = track.channel;
    copy.append(title, channel);

    const duration = document.createElement('time');
    duration.textContent = formatTime(track.duration_seconds);
    item.append(position, image, copy, duration);
    elements.queue.append(item);
  });
}

function render(snapshot) {
  runtime.snapshot = snapshot;
  runtime.fetchedAt = Date.now();
  const { playback, video, queue, modes } = snapshot;

  if (!video) {
    unmountVideo('Aguardando a próxima música', 'Inicie a reprodução pelo painel do bot.');
    elements.title.textContent = 'Nenhuma música tocando';
    elements.channel.textContent = 'A sala continuará conectada.';
    setSyncState('waiting', 'Aguardando música');
  } else {
    elements.title.textContent = video.title;
    elements.channel.textContent = video.channel;
    if (runtime.videoId !== video.video_id) {
      mountVideo(video.video_id, playback.position_seconds, playback.status);
    } else if (runtime.playbackStatus !== playback.status) {
      playerCommand(playback.status === 'playing' ? 'playVideo' : 'pauseVideo');
      runtime.playbackStatus = playback.status;
      hardSync();
    } else if (
      runtime.playerReady
      && Number.isFinite(runtime.playerPosition)
      && Math.abs(runtime.playerPosition - desiredPosition()) > 2.5
      && Date.now() - runtime.lastHardSyncAt > 5000
    ) {
      hardSync();
    } else if (runtime.playerReady && Date.now() - runtime.lastHardSyncAt > 30000) {
      hardSync();
    }

    if (playback.status === 'playing') setSyncState('live', 'Sincronizado ao vivo');
    else if (playback.status === 'paused') setSyncState('paused', 'Áudio pausado');
    else setSyncState('waiting', 'Preparando áudio');
  }

  elements.duration.textContent = formatTime(playback.duration_seconds);
  elements.mode.textContent = modes.shuffle ? 'Shuffle ligado' : 'Ordem normal';
  elements.mode.classList.toggle('active', modes.shuffle);
  renderQueue(queue);
  updateProgress();
}

function updateProgress() {
  const playback = runtime.snapshot?.playback;
  if (!playback) return;
  const position = Math.min(desiredPosition(), playback.duration_seconds || Infinity);
  const ratio = playback.duration_seconds ? position / playback.duration_seconds : 0;
  elements.progress.style.width = `${Math.min(100, Math.max(0, ratio * 100))}%`;
  elements.elapsed.textContent = formatTime(position);
}

async function fetchSnapshot() {
  if (!runtime.guildId) return;
  const response = await fetch(
    `${apiPath('/api/state')}?guild_id=${encodeURIComponent(runtime.guildId)}`,
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error(`Estado indisponível (${response.status})`);
  render(await response.json());
}

async function initialize() {
  try {
    const configResponse = await fetch(apiPath('/api/config'), { cache: 'no-store' });
    if (!configResponse.ok) throw new Error('Configuração da Activity indisponível');
    runtime.config = await configResponse.json();

    if (runtime.embedded && runtime.config.client_id) {
      patchUrlMappings(
        [
          { prefix: '/youtube', target: 'www.youtube.com' },
          { prefix: '/ytimg', target: 'img.youtube.com' },
        ],
        { patchSrcAttributes: true },
      );
      runtime.discord = new DiscordSDK(runtime.config.client_id);
      await runtime.discord.ready();
      runtime.guildId = runtime.discord.guildId || runtime.guildId;
    }

    if (!runtime.guildId) {
      unmountVideo(
        'Abra a Activity em um servidor',
        'Entre em um canal de voz e use o botão “Abrir clipe” no painel do bot.',
      );
      setSyncState('error', 'Servidor não identificado');
      return;
    }

    await fetchSnapshot();
    runtime.timer = window.setInterval(async () => {
      try {
        await fetchSnapshot();
      } catch (error) {
        console.error(error);
        setSyncState('error', 'Reconectando');
      }
    }, runtime.config.poll_interval_ms || 2000);
  } catch (error) {
    console.error(error);
    unmountVideo('Não foi possível conectar', 'Verifique a configuração da Activity e tente novamente.');
    setSyncState('error', 'Sem conexão');
  }
}

window.addEventListener('message', (event) => {
  if (!runtime.iframe || event.source !== runtime.iframe.contentWindow) return;
  let payload = event.data;
  if (typeof payload === 'string') {
    try {
      payload = JSON.parse(payload);
    } catch {
      return;
    }
  }
  if (!payload || typeof payload !== 'object') return;

  if (payload.event === 'onReady') {
    runtime.playerReady = true;
    window.clearTimeout(runtime.playerReadyTimer);
    elements.empty.hidden = true;
    hardSync();
    return;
  }
  if (payload.event === 'onError') {
    runtime.playerReady = false;
    window.clearTimeout(runtime.playerReadyTimer);
    showPlayerError(payload.info);
    return;
  }
  if (payload.event === 'infoDelivery' && Number.isFinite(payload.info?.currentTime)) {
    runtime.playerPosition = payload.info.currentTime;
  }
});

elements.resync.addEventListener('click', hardSync);
elements.fullscreen.addEventListener('click', toggleVideoFullscreen);
elements.youtube.addEventListener('click', async () => {
  const url = runtime.snapshot?.video?.url;
  if (!url) return;
  try {
    if (runtime.discord) {
      await runtime.discord.commands.openExternalLink({ url });
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  } catch (error) {
    console.error(error);
    flashNotice('Não foi possível abrir o YouTube neste dispositivo.');
  }
});
document.addEventListener('fullscreenchange', updateFullscreenButton);
document.addEventListener('webkitfullscreenchange', updateFullscreenButton);
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && elements.videoFrame.classList.contains('fullscreen-fallback')) {
    exitFallbackFullscreen();
  }
});
window.setInterval(updateProgress, 500);
window.addEventListener('beforeunload', () => {
  window.clearInterval(runtime.timer);
  window.clearTimeout(runtime.playerReadyTimer);
});

initialize();
