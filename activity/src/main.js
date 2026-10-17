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
  controlDeck: document.querySelector('#control-deck'),
  controlAuthNotice: document.querySelector('#control-auth-notice'),
  playPause: document.querySelector('#play-pause-control'),
  playPauseIcon: document.querySelector('#play-pause-icon'),
  playPauseLabel: document.querySelector('#play-pause-label'),
  stopControl: document.querySelector('#stop-control'),
  shuffleControl: document.querySelector('#shuffle-control'),
  repeatControl: document.querySelector('#repeat-control'),
  volumeControl: document.querySelector('#volume-control'),
  volumeLabel: document.querySelector('#volume-label'),
  addForm: document.querySelector('#add-form'),
  addQuery: document.querySelector('#add-query'),
  addSubmit: document.querySelector('#add-submit'),
  searchResults: document.querySelector('#search-results'),
  resync: document.querySelector('#resync-button'),
  youtube: document.querySelector('#youtube-button'),
  fullscreen: document.querySelector('#fullscreen-button'),
  notice: document.querySelector('#notice'),
};

const runtime = {
  embedded: new URLSearchParams(window.location.search).has('frame_id'),
  discord: null,
  guildId: new URLSearchParams(window.location.search).get('guild_id'),
  controlToken: new URLSearchParams(window.location.search).get('control_token'),
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
  controlBusy: false,
  searchController: null,
};

function apiPath(path) {
  return `${runtime.embedded ? '/.proxy' : ''}${path}`;
}

function apiHeaders(extra = {}) {
  return {
    ...extra,
    ...(runtime.controlToken ? { 'X-Loki-Control': runtime.controlToken } : {}),
  };
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
    copy.className = 'queue-copy';
    const title = document.createElement('strong');
    title.textContent = track.title;
    const channel = document.createElement('span');
    channel.textContent = track.channel;
    copy.append(title, channel);

    const duration = document.createElement('time');
    duration.textContent = formatTime(track.duration_seconds);

    const actions = document.createElement('div');
    actions.className = 'queue-actions';
    const promote = document.createElement('button');
    promote.type = 'button';
    promote.className = 'queue-action promote-action';
    promote.title = 'Tocar em seguida';
    promote.setAttribute('aria-label', `Tocar ${track.title} em seguida`);
    promote.textContent = '⏫';
    promote.addEventListener('click', () => controlRequest('promote', { video_id: track.video_id }));
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'queue-action remove-action';
    remove.title = 'Remover da fila';
    remove.setAttribute('aria-label', `Remover ${track.title} da fila`);
    remove.textContent = '×';
    remove.addEventListener('click', () => controlRequest('remove', { video_id: track.video_id }));
    actions.append(promote, remove);

    const meta = document.createElement('div');
    meta.className = 'queue-meta';
    meta.append(duration, actions);
    item.append(position, image, copy, meta);
    elements.queue.append(item);
  });
}

function renderControls(snapshot) {
  const { playback, modes, controls } = snapshot;
  const authorized = Boolean(controls?.authorized);
  elements.controlDeck.classList.toggle('read-only', !authorized);
  elements.controlAuthNotice.hidden = authorized;
  document.querySelectorAll('[data-control], [data-control-input]').forEach((control) => {
    control.disabled = !authorized || runtime.controlBusy;
  });

  const playing = playback.status === 'playing';
  elements.playPauseIcon.textContent = playing ? '⏸' : '▶';
  elements.playPauseLabel.textContent = playing ? 'Pausar' : 'Tocar';
  elements.stopControl.disabled = !authorized || runtime.controlBusy || !controls?.connected;
  elements.shuffleControl.classList.toggle('active', Boolean(modes.shuffle));

  const repeatLabels = {
    off: 'Repetir: desligado',
    one: 'Repetir: esta faixa',
    all: 'Repetir: todas',
  };
  elements.repeatControl.classList.toggle('active', modes.repeat !== 'off');
  elements.repeatControl.lastChild.textContent = ` ${repeatLabels[modes.repeat] || repeatLabels.off}`;

  const volume = Number(controls?.volume_percent ?? 25);
  if (document.activeElement !== elements.volumeControl) elements.volumeControl.value = volume;
  elements.volumeLabel.value = `${volume}%`;
  elements.volumeLabel.textContent = `${volume}%`;
  elements.queue.querySelectorAll('button').forEach((button) => {
    button.disabled = !authorized || runtime.controlBusy;
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
  renderControls(snapshot);
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
    { cache: 'no-store', headers: apiHeaders() },
  );
  if (!response.ok) throw new Error(`Estado indisponível (${response.status})`);
  render(await response.json());
}

async function responsePayload(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  return { error: await response.text() };
}

async function controlRequest(action, payload = {}) {
  if (!runtime.controlToken || runtime.controlBusy) {
    if (!runtime.controlToken) flashNotice('Abra o painel pelo botão do bot para controlar a sala.');
    return false;
  }
  runtime.controlBusy = true;
  if (runtime.snapshot) renderControls(runtime.snapshot);
  try {
    const response = await fetch(
      `${apiPath('/api/control')}?guild_id=${encodeURIComponent(runtime.guildId)}`,
      {
        method: 'POST',
        headers: apiHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ action, ...payload }),
      },
    );
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(data.error || 'Não foi possível executar o comando.');
    if (data.state) render(data.state);
    flashNotice(data.message || 'Comando executado.');
    return true;
  } catch (error) {
    console.error(error);
    flashNotice(error.message || 'Não foi possível executar o comando.');
    return false;
  } finally {
    runtime.controlBusy = false;
    if (runtime.snapshot) renderControls(runtime.snapshot);
  }
}

function youtubeVideoId(value) {
  const trimmed = value.trim();
  if (/^[A-Za-z0-9_-]{11}$/.test(trimmed)) return trimmed;
  try {
    const url = new URL(trimmed);
    if (url.hostname === 'youtu.be') return url.pathname.split('/').filter(Boolean)[0] || null;
    if (url.hostname.endsWith('youtube.com')) {
      return url.searchParams.get('v') || url.pathname.match(/\/(?:shorts|embed)\/([A-Za-z0-9_-]{11})/)?.[1] || null;
    }
  } catch {
    return null;
  }
  return null;
}

function renderSearchResults(results) {
  elements.searchResults.replaceChildren();
  elements.searchResults.hidden = false;
  if (!results.length) {
    elements.searchResults.textContent = 'Nenhum resultado encontrado.';
    return;
  }
  results.forEach((result) => {
    const item = document.createElement('article');
    item.className = 'search-result';
    const image = document.createElement('img');
    image.src = result.thumbnail_url;
    image.alt = '';
    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = result.title;
    const detail = document.createElement('span');
    detail.textContent = [result.channel, result.duration].filter(Boolean).join(' · ');
    copy.append(title, detail);
    const add = document.createElement('button');
    add.type = 'button';
    add.textContent = 'Adicionar';
    add.addEventListener('click', async () => {
      if (await controlRequest('add', { video_id: result.video_id })) {
        elements.searchResults.hidden = true;
        elements.addQuery.value = '';
      }
    });
    item.append(image, copy, add);
    elements.searchResults.append(item);
  });
}

async function searchSongs(query) {
  runtime.searchController?.abort();
  runtime.searchController = new AbortController();
  elements.addSubmit.disabled = true;
  elements.addSubmit.textContent = 'Buscando…';
  try {
    const response = await fetch(
      `${apiPath('/api/search')}?guild_id=${encodeURIComponent(runtime.guildId)}&q=${encodeURIComponent(query)}`,
      { headers: apiHeaders(), signal: runtime.searchController.signal },
    );
    const data = await responsePayload(response);
    if (!response.ok) throw new Error(data.error || 'Não foi possível pesquisar.');
    renderSearchResults(data.results || []);
  } catch (error) {
    if (error.name !== 'AbortError') flashNotice(error.message || 'Não foi possível pesquisar.');
  } finally {
    elements.addSubmit.textContent = '＋ Adicionar';
    elements.addSubmit.disabled = !runtime.controlToken;
  }
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
document.querySelectorAll('[data-control]').forEach((button) => {
  button.addEventListener('click', () => {
    const action = button.dataset.control;
    if (action === 'clear' && !window.confirm('Remover todas as músicas da fila?')) return;
    controlRequest(action);
  });
});
elements.volumeControl.addEventListener('input', () => {
  elements.volumeLabel.value = `${elements.volumeControl.value}%`;
  elements.volumeLabel.textContent = `${elements.volumeControl.value}%`;
});
elements.volumeControl.addEventListener('change', () => {
  controlRequest('volume', { value: elements.volumeControl.value });
});
elements.addForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const query = elements.addQuery.value.trim();
  if (query.length < 2) {
    flashNotice('Digite o nome ou cole um link do YouTube.');
    return;
  }
  const videoId = youtubeVideoId(query);
  if (videoId) controlRequest('add', { video_id: videoId });
  else searchSongs(query);
});
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
