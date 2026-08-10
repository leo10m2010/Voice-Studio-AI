import "./styles.css";

const API = "http://127.0.0.1:8765";
const DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base";
const REQUIRED_ENGINE_VERSION = "1.0.2";

const icons = {
  wave: `<svg viewBox="0 0 24 24"><path d="M4 13v-2M8 17V7M12 20V4M16 16V8M20 13v-2"/></svg>`,
  play: `<svg viewBox="0 0 24 24"><path d="m9 7 8 5-8 5V7Z"/></svg>`,
  pause: `<svg viewBox="0 0 24 24"><path d="M9 8v8M15 8v8"/></svg>`,
  chevron: `<svg viewBox="0 0 24 24"><path d="m8 10 4 4 4-4"/></svg>`,
  back: `<svg viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>`,
  search: `<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg>`,
  plus: `<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>`,
  download: `<svg viewBox="0 0 24 24"><path d="M12 4v11M8 11l4 4 4-4M5 20h14"/></svg>`,
  history: `<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 3-6M4 4v5h5"/><path d="M12 8v5l3 2"/></svg>`,
  cpu: `<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M18 9h4M2 15h4M18 15h4M10 10h4v4h-4z"/></svg>`,
  check: `<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>`,
  spark: `<svg viewBox="0 0 24 24"><path d="M12 3l1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4L12 3Z"/></svg>`,
  trash: `<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13"/></svg>`,
  moon: `<svg viewBox="0 0 24 24"><path d="M20 15.5A8 8 0 1 1 8.5 4 6.5 6.5 0 0 0 20 15.5Z"/></svg>`,
  sun: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`,
  info: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>`,
  music: `<svg viewBox="0 0 24 24"><path d="M9 18V6l10-2v12M9 18a3 3 0 1 1-3-3h3M19 16a3 3 0 1 1-3-3h3"/></svg>`,
  volume: `<svg viewBox="0 0 24 24"><path d="M5 10v4h4l5 4V6L9 10H5Z"/><path d="M17 9a4 4 0 0 1 0 6"/></svg>`,
  model: `<svg viewBox="0 0 24 24"><path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z"/><path d="m4 7 8 4 8-4M12 11v10"/></svg>`,
  external: `<svg viewBox="0 0 24 24"><path d="M14 5h5v5M19 5l-8 8"/><path d="M18 13v6H5V6h6"/></svg>`,
  package: `<svg viewBox="0 0 24 24"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/></svg>`,
  shield: `<svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-5"/></svg>`,
  wifi: `<svg viewBox="0 0 24 24"><path d="M5 9a11 11 0 0 1 14 0M8 12a7 7 0 0 1 8 0M11 15a2.5 2.5 0 0 1 2 0"/><circle cx="12" cy="18" r=".8" fill="currentColor" stroke="none"/></svg>`,
  refresh: `<svg viewBox="0 0 24 24"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 7M5.5 15A7 7 0 0 0 18 17"/></svg>`,
  close: `<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>`
};

const state = {
  voices: [],
  sounds: [],
  history: [],
  models: { recommended_id: DEFAULT_MODEL_ID, compatible: [], discovery: [] },
  model: null,
  voice: null,
  result: null,
  preview: null,
  busy: false,
  statusTimer: null,
  profile: "natural",
  pendingVoiceFile: null,
  waveform: [],
  waveformUrl: null,
  seeking: false,
  modelSearchTimer: null,
  modelInstallTimer: null,
  modelInstallId: null,
  activeSheet: null,
  selectedSoundId: "",
  musicBusy: false,
  generationRequestId: null,
  generationController: null,
  engine: {
    status: null,
    catalog: null,
    hardware: null,
    selectedFlavor: "cpu",
    installing: false,
    bridgeReady: false,
    bootStarted: false,
    recovering: false
  }
};

document.querySelector("#app").innerHTML = `
  <main class="app-shell">
    <header class="app-header glass">
      <div class="brand">
        <span class="brand-icon">${icons.wave}</span>
        <div>
          <strong>Voice Studio AI</strong>
          <small>Clonación y locución local · Qwen recomendado</small>
        </div>
      </div>

      <div class="header-center">
        <div class="hardware-chip">
          ${icons.cpu}
          <span id="hardwareText">Detectando equipo…</span>
        </div>
      </div>

      <button class="icon-button pressable" id="themeButton" aria-label="Cambiar tema">${icons.moon}</button>
    </header>

    <section class="main-grid">
      <section class="editor-pane">
        <div class="editor-scroll">
          <div class="editor-canvas">
            <textarea id="scriptInput" maxlength="3000"
              placeholder="Escribe o pega aquí el guion que quieres convertir en voz…"></textarea>

            <div class="editor-meta">
              <span id="characterCount">0 / 3000</span>
              <span id="durationEstimate">≈ 0 s</span>
              <span id="iclStatus">Selecciona una voz</span>
            </div>

            <div class="quick-prompts">
              <button class="pressable" data-prompt="¡Atención, Huánuco! Hoy celebramos con orgullo nuestra historia, nuestra cultura y nuestra gente. ¡Feliz aniversario!">Spot 10 s</button>
              <button class="pressable" data-prompt="Bienvenidos. En los próximos minutos conoceremos una historia que merece ser contada con calma, claridad y una voz cercana.">Narración</button>
              <button class="pressable" data-prompt="¿Estás listo? Porque lo que viene ahora cambia por completo la forma de escuchar esta historia.">Expresivo</button>
            </div>

            <div class="script-guidance">
              <span>${icons.info}</span>
              <p><strong>Español:</strong> escribe como quieres que suene. Puntos para pausas claras, comas para pausas cortas y exclamaciones con moderación.</p>
            </div>
          </div>
        </div>

        <div class="generation-strip" id="generationStrip" aria-live="polite">
          <div class="mini-orb" id="thinkingOrb">
            <span class="mini-orb-core"></span>
            <span class="mini-orb-ring"></span>
          </div>
          <div class="generation-copy">
            <strong id="generationTitle">Generando locución</strong>
            <span id="generationText">Preparando el motor…</span>
          </div>
          <span class="generation-engine" id="generationEngine">LOCAL</span>
          <button class="strip-cancel pressable" id="cancelGeneration" type="button" title="Cancelar generación" hidden>${icons.close}</button>
        </div>

        <div class="bottom-dock glass">
          <div class="selected-voice-mini">
            <span class="voice-avatar">${icons.wave}</span>
            <div>
              <strong id="bottomVoice">Sin voz seleccionada</strong>
              <small id="bottomMode">Qwen3-TTS 0.6B Base</small>
            </div>
          </div>

          <div class="transport" id="transport">
            <button class="generate-main pressable" id="generateButton" disabled>
              <span id="generateIcon">${icons.spark}</span>
              <span id="generateText">Generar</span>
              <kbd>Ctrl ↵</kbd>
            </button>

            <div class="audio-player" id="audioPlayer">
              <button class="player-play pressable" id="playerPlay" aria-label="Reproducir">${icons.play}</button>
              <span class="player-time" id="playerCurrent">0:00</span>
              <canvas class="waveform" id="waveform" width="700" height="58" aria-label="Forma de onda"></canvas>
              <span class="player-time" id="playerDuration">0:00</span>
              <div class="volume-wrap music-wrap">
                <button class="player-icon pressable" id="musicButton" aria-label="Música de fondo">${icons.music}</button>
                <div class="volume-popover music-popover" id="musicPopover">
                  <label class="music-popover-label">Música de fondo</label>
                  <div class="sound-picker-row">
                    <div class="select-native">
                      <select id="soundSelect"><option value="">Sin música</option></select>
                      ${icons.chevron}
                    </div>
                    <button class="icon-button pressable" id="previewSound" title="Escuchar">${icons.play}</button>
                    <button class="icon-button pressable" id="addSound" title="Agregar música">${icons.plus}</button>
                  </div>
                  <div class="slider-setting music-volume-setting">
                    <div class="slider-title"><label>Volumen</label><output id="musicVolumeValue">18%</output></div>
                    <input id="musicVolume" type="range" min="5" max="40" value="18" step="1">
                  </div>
                  <p class="music-status" id="musicStatus">Elige una pista y aplícala a esta locución ya generada.</p>
                  <button class="repair-library pressable" id="repairSounds" type="button">Reparar biblioteca de música</button>
                  <div class="music-popover-actions">
                    <button class="secondary-button pressable" id="removeMusic" type="button" disabled>Quitar música</button>
                    <button class="secondary-button pressable apply-music" id="applyMusic" type="button" disabled>Aplicar música</button>
                  </div>
                </div>
              </div>
              <div class="volume-wrap">
                <button class="player-icon pressable" id="volumeButton" aria-label="Volumen">${icons.volume}</button>
                <div class="volume-popover" id="volumePopover">
                  <input id="playerVolume" type="range" min="0" max="1" value="1" step="0.01">
                </div>
              </div>
              <a class="player-icon pressable disabled" id="downloadButton" href="#" download aria-label="Guardar audio">${icons.download}</a>
            </div>

            <audio id="resultAudio" preload="metadata"></audio>
          </div>
        </div>
      </section>

      <aside class="side-pane">
        <div class="tabs" id="tabs" data-active="settings">
          <span class="tab-indicator"></span>
          <button class="active pressable" data-tab="settings">Ajustes</button>
          <button class="pressable" data-tab="history">Historial</button>
        </div>

        <div class="side-content">
          <section id="settingsPanel" class="tab-panel active">
            <div class="setting-block">
              <label>Voz</label>
              <button class="select-card pressable" id="voiceSelector">
                <span class="voice-avatar">${icons.wave}</span>
                <span class="select-card-copy">
                  <strong id="selectedVoiceName">Selecciona una voz</strong>
                  <small id="selectedVoiceMeta">Mis voces</small>
                </span>
                <span class="chevron">${icons.chevron}</span>
              </button>
            </div>

            <div class="reference-card" id="referenceCard">
              <div class="reference-score" id="referenceScore"><strong>—</strong><small>/100</small></div>
              <div class="reference-copy">
                <span class="eyebrow">Calidad de referencia</span>
                <strong id="referenceLabel">Selecciona una voz</strong>
                <small id="referenceDetails">Duración, nivel, clipping y transcripción.</small>
              </div>
              <button class="reference-action pressable" id="improveClone" disabled>Revisar</button>
            </div>

            <div class="setting-block model-setting-block">
              <label>Modelo</label>
              <button class="select-card model-select-card pressable" id="modelSelector">
                <span class="model-avatar" id="selectedModelAvatar"><span>Q</span></span>
                <span class="select-card-copy">
                  <strong id="selectedModelName">Qwen3-TTS 0.6B Base</strong>
                  <small id="selectedModelMeta">Recomendado · Compatible</small>
                </span>
                <span class="chevron">${icons.chevron}</span>
              </button>
            </div>

            <div class="model-install-card" id="modelInstallCard" data-state="checking" aria-live="polite">
              <span class="model-install-icon">${icons.model}</span>
              <span class="model-install-copy">
                <small>MODELO DE VOZ</small>
                <strong id="modelInstallTitle">Comprobando modelo…</strong>
                <span id="modelInstallMeta">Buscando archivos locales.</span>
              </span>
              <button class="model-install-action pressable" id="installSelectedModel" type="button" disabled>
                Comprobando
              </button>
            </div>

            <div class="engine-mini-card" id="engineMiniCard">
              <span class="engine-mini-icon">${icons.package}</span>
              <span class="engine-mini-copy">
                <small>MOTOR LOCAL</small>
                <strong id="engineMiniTitle">Comprobando…</strong>
                <span id="engineMiniMeta">Python y PyTorch privados de Voice Studio AI</span>
              </span>
              <button class="engine-mini-action pressable" id="manageEngine" type="button">Gestionar</button>
            </div>

            <div class="setting-block">
              <div class="label-row">
                <label>Perfil</label>
                <button class="help" data-tip="Fiel prioriza consistencia. Natural es el punto de partida. Spot añade una variación moderada sin exagerar el muestreo.">${icons.info}</button>
              </div>
              <div class="profile-buttons" id="profileButtons">
                <button class="pressable" data-profile="faithful">Fiel</button>
                <button class="active pressable" data-profile="natural">Natural</button>
                <button class="pressable" data-profile="spot">Spot</button>
              </div>
            </div>

            <div class="slider-setting">
              <div class="slider-title"><label>Velocidad</label><output id="speedValue">1.00×</output></div>
              <div class="slider-hints"><span>Más lento</span><span>Más rápido</span></div>
              <input id="speed" type="range" min="0.80" max="1.20" step="0.01" value="1.00">
            </div>

            <div class="slider-setting">
              <div class="slider-title">
                <label>Estabilidad</label>
                <button class="help" data-tip="Controla el muestreo real de Qwen. Más estabilidad reduce variación; demasiada puede sonar plana.">${icons.info}</button>
              </div>
              <div class="slider-hints"><span>Más variable</span><span>Más estable</span></div>
              <input id="stability" type="range" min="0" max="100" step="1" value="55">
            </div>

            <div class="slider-setting">
              <div class="slider-title">
                <label>Expresividad</label>
                <button class="help" data-tip="Qwen Base no tiene un control nativo de emoción. Se modifica de forma conservadora el muestreo; valores altos pueden reducir estabilidad.">${icons.info}</button>
              </div>
              <div class="slider-hints"><span>Natural</span><span>Más variación</span></div>
              <input id="style" type="range" min="0" max="100" step="1" value="0">
            </div>

            <div class="slider-setting">
              <div class="slider-title"><label>Tono / Altura</label><output id="pitchValue">0.0 st</output></div>
              <div class="slider-hints"><span>Más grave</span><span>Más brillante</span></div>
              <input id="pitch" type="range" min="-3" max="3" step="0.25" value="0">
              <p class="setting-note">Postproceso local. Para máxima fidelidad, déjalo en 0.</p>
            </div>

            <div class="setting-block compact-top">
              <label>Formato</label>
              <div class="select-native">
                <select id="outputFormat">
                  <option value="wav">WAV · sin pérdida</option>
                  <option value="flac">FLAC · sin pérdida</option>
                </select>
                ${icons.chevron}
              </div>
            </div>

            <div class="toggle-row">
              <div><label>Realce de voz</label><small>Presencia y normalización local</small></div>
              <button class="toggle on pressable" id="speakerBoost" aria-pressed="true"><span></span></button>
            </div>

            <details class="advanced">
              <summary>Avanzado / Motor</summary>
              <div class="advanced-content">
                <label>Procesamiento</label>
                <div class="select-native">
                  <select id="mode">
                    <option value="auto">Automático</option>
                    <option value="cuda">GPU experimental</option>
                    <option value="cpu">CPU</option>
                  </select>${icons.chevron}
                </div>
                <p>Automático compara la VRAM disponible con el modelo seleccionado.</p>
              </div>
            </details>

            <div class="settings-footer">
              <button class="pressable" id="resetSettings">${icons.history}<span>Restablecer valores</span></button>
            </div>
          </section>

          <section id="historyPanel" class="tab-panel">
            <div class="history-toolbar">
              <div class="search-box">${icons.search}<input id="historySearch" placeholder="Buscar en historial…"></div>
              <button class="icon-button small pressable" id="clearHistory" title="Borrar historial">${icons.trash}</button>
            </div>
            <div class="history-list" id="historyList"></div>
          </section>
        </div>


<section class="side-sheet" id="selectorSheet" aria-hidden="true">
  <div class="sheet-header">
    <button class="icon-button small pressable" id="selectorBack" aria-label="Volver a Ajustes" title="Volver a Ajustes">${icons.back}</button>
    <div>
      <strong id="selectorTitle">Seleccionar</strong>
      <small id="selectorSubtitle">Ajustes</small>
    </div>
  </div>

  <div class="sheet-view" id="voiceSheetView" hidden>
    <div class="search-box">${icons.search}<input id="voiceSearch" placeholder="Buscar voces…"></div>
    <div class="sheet-toolbar">
      <button class="secondary-button pressable" id="addVoice">${icons.plus}<span>Agregar voz</span></button>
    </div>
    <div class="sheet-list" id="voiceList"></div>
  </div>

  <div class="sheet-view" id="modelSheetView" hidden>
    <div class="model-section">
      <span class="section-label">Compatibles ahora</span>
      <div class="sheet-list model-list" id="compatibleModelList"></div>
    </div>

    <div class="model-section hf-section">
      <div class="section-label-row">
        <span class="section-label">Buscar en Hugging Face</span>
        <span class="online-badge">ONLINE</span>
      </div>
      <div class="search-box">${icons.search}<input id="modelSearch" placeholder="Ej.: Chatterbox, OpenVoice, Qwen…"></div>
      <div class="search-state" id="modelSearchState">Busca modelos TTS del Hub. Los que requieran otra API se marcarán como “Adaptador”.</div>
      <div class="sheet-list model-list" id="modelSearchResults"></div>
    </div>
  </div>
</section>

      </aside>
    </section>

    <dialog id="transcriptDialog">
      <form method="dialog" class="modal-card" id="transcriptForm">
        <div class="modal-head">
          <div><span class="eyebrow">Referencia de voz</span><h2>Mejorar clonación</h2></div>
          <button value="cancel" class="modal-close pressable">×</button>
        </div>
        <p>Escribe exactamente lo que se escucha en el audio. Qwen usará audio + texto en modo ICL.</p>
        <label>Transcripción exacta
          <textarea id="transcriptInput" maxlength="1800" placeholder="Ejemplo: ¡Atención, Huánuco! Hoy celebramos juntos nuestro aniversario."></textarea>
        </label>
        <div class="modal-actions">
          <button type="button" class="danger-text pressable" id="removeTranscript">Quitar transcripción</button>
          <span></span>
          <button value="cancel" class="secondary pressable">Cancelar</button>
          <button value="default" class="primary pressable" id="saveTranscript">Guardar</button>
        </div>
      </form>
    </dialog>

    <dialog id="voiceImportDialog">
      <form method="dialog" class="modal-card" id="voiceImportForm">
        <div class="modal-head">
          <div><span class="eyebrow">Nueva referencia</span><h2>Preparar voz</h2></div>
          <button value="cancel" class="modal-close pressable">×</button>
        </div>
        <div class="import-summary" id="importSummary"></div>
        <ul class="import-tips">
          <li>Una sola persona y sin música.</li>
          <li>Ideal práctico: 8–25 segundos limpios.</li>
          <li>La transcripción exacta activa ICL y suele mejorar la fidelidad.</li>
        </ul>
        <label>Transcripción exacta
          <textarea id="importTranscript" maxlength="1800" placeholder="Escribe exactamente lo que se escucha en el audio…"></textarea>
        </label>
        <div class="modal-actions">
          <span></span><span></span>
          <button value="cancel" class="secondary pressable">Cancelar</button>
          <button value="default" class="primary pressable" id="confirmVoiceImport">Importar y preparar</button>
        </div>
      </form>
    </dialog>


    <section class="engine-setup" id="engineSetup" aria-hidden="true">
      <div class="engine-setup-backdrop"></div>
      <div class="engine-setup-card" role="dialog" aria-modal="true" aria-labelledby="engineSetupTitle">
        <div class="setup-brand">
          <span class="setup-logo">${icons.wave}</span>
          <div>
            <strong>Voice Studio AI</strong>
            <small>Configuración del motor local</small>
          </div>
          <button class="setup-close pressable" id="engineSetupClose" type="button" aria-label="Cerrar" hidden>×</button>
        </div>

        <div class="setup-view active" id="engineIntroView">
          <div class="setup-hero">
            <span class="setup-kicker" id="setupIntroKicker">PRIMER INICIO</span>
            <h1 id="engineSetupTitle">Preparamos el estudio por ti.</h1>
            <p id="setupIntroBody">Voice Studio AI descargará su motor de voz de forma segura. No necesitas instalar Python, PyTorch ni abrir una terminal.</p>
          </div>

          <div class="setup-hardware-card">
            <span class="setup-hardware-icon">${icons.cpu}</span>
            <div>
              <small>TU EQUIPO</small>
              <strong id="setupHardwareName">Detectando hardware…</strong>
              <span id="setupHardwareMeta">Buscando la mejor configuración.</span>
            </div>
            <span class="setup-recommended" id="setupRecommended">AUTO</span>
          </div>

          <div class="engine-flavors" id="engineFlavorList">
            <div class="setup-skeleton"></div>
            <div class="setup-skeleton"></div>
          </div>

          <div class="setup-trust-row">
            <span>${icons.shield}</span>
            <p><strong>Instalación privada.</strong> El runtime de Python queda dentro de Voice Studio AI y no modifica Python ni CUDA del sistema.</p>
          </div>

          <div class="setup-actions">
            <div class="setup-size">
              <small>DESCARGA</small>
              <strong id="setupDownloadSize">Calculando…</strong>
            </div>
            <button class="setup-primary pressable" id="installEngineButton" type="button" disabled>
              Preparar Voice Studio AI
            </button>
          </div>

          <p class="setup-error" id="engineCatalogError" hidden></p>
        </div>

        <div class="setup-view" id="engineProgressView">
          <div class="setup-progress-hero">
            <span class="setup-orb"><i></i><b></b></span>
            <span class="setup-kicker" id="setupProgressKicker">PREPARANDO MOTOR</span>
            <h1 id="setupProgressTitle">Descargando componentes…</h1>
            <p id="setupProgressMessage">Esto puede tardar unos minutos. Puedes seguir el progreso aquí.</p>
          </div>

          <div class="setup-progress-track">
            <span id="setupProgressBar"></span>
          </div>

          <div class="setup-progress-meta">
            <strong id="setupProgressPercent">0%</strong>
            <span id="setupProgressBytes">0 MB</span>
          </div>

          <div class="setup-steps" id="setupSteps">
            <div data-step="downloading"><i>${icons.download}</i><span>Descargar</span><b>En espera</b></div>
            <div data-step="verifying"><i>${icons.shield}</i><span>Verificar</span><b>En espera</b></div>
            <div data-step="installing"><i>${icons.package}</i><span>Instalar</span><b>En espera</b></div>
            <div data-step="testing"><i>${icons.check}</i><span>Comprobar</span><b>En espera</b></div>
          </div>

          <button class="setup-cancel pressable" id="cancelEngineInstall" type="button">Cancelar descarga</button>
        </div>

        <div class="setup-view" id="engineDoneView">
          <div class="setup-complete">
            <span class="setup-complete-icon">${icons.check}</span>
            <span class="setup-kicker">TODO LISTO</span>
            <h1>Tu estudio está preparado.</h1>
            <p id="setupDoneMeta">El motor local fue instalado y comprobado correctamente.</p>
            <button class="setup-primary pressable" id="enterStudioButton" type="button">Entrar a Voice Studio AI</button>
          </div>
        </div>

        <div class="setup-view" id="engineManageView">
          <div class="setup-hero manage">
            <span class="setup-kicker">MOTOR LOCAL</span>
            <h1>Componentes de Voice Studio AI</h1>
            <p>Administra el motor sin tocar Python, controladores ni archivos del sistema.</p>
          </div>

          <div class="engine-installed-card">
            <span class="setup-complete-icon small">${icons.check}</span>
            <div>
              <small>INSTALADO</small>
              <strong id="manageEngineTitle">Motor local</strong>
              <span id="manageEngineMeta">Comprobando versión…</span>
            </div>
          </div>

          <div class="manage-actions">
            <button class="secondary-button pressable" id="repairEngineButton" type="button">${icons.refresh}<span>Reparar / actualizar</span></button>
            <button class="danger-outline pressable" id="uninstallEngineButton" type="button">${icons.trash}<span>Desinstalar motor</span></button>
          </div>

          <div class="setup-trust-row compact">
            <span>${icons.info}</span>
            <p>Tus voces, música, historial y modelos descargados se guardan aparte. Reparar o desinstalar el motor no borra esos datos.</p>
          </div>
        </div>
      </div>
    </section>

    <input id="voiceFile" type="file" accept=".wav,.mp3,.flac,.ogg" hidden>
    <input id="soundFile" type="file" accept=".wav,.mp3,.flac,.ogg" hidden>
    <div class="tooltip" id="tooltip"></div>
    <div class="toast" id="toast"></div>
  </main>
`;

const $ = q => document.querySelector(q);
const $$ = q => [...document.querySelectorAll(q)];

const el = {
  script: $("#scriptInput"), count: $("#characterCount"), duration: $("#durationEstimate"), icl: $("#iclStatus"),
  strip: $("#generationStrip"), stripTitle: $("#generationTitle"), stripText: $("#generationText"), stripEngine: $("#generationEngine"), orb: $("#thinkingOrb"), cancelGeneration: $("#cancelGeneration"),
  generate: $("#generateButton"), generateIcon: $("#generateIcon"), generateText: $("#generateText"), transport: $("#transport"),
  audio: $("#resultAudio"), player: $("#audioPlayer"), playerPlay: $("#playerPlay"), playerCurrent: $("#playerCurrent"),
  playerDuration: $("#playerDuration"), waveform: $("#waveform"), volumeButton: $("#volumeButton"), volumePopover: $("#volumePopover"),
  musicButton: $("#musicButton"), musicPopover: $("#musicPopover"), applyMusic: $("#applyMusic"), removeMusic: $("#removeMusic"),
  playerVolume: $("#playerVolume"), download: $("#downloadButton"), bottomVoice: $("#bottomVoice"), bottomMode: $("#bottomMode"),
  hardware: $("#hardwareText"), voiceSelector: $("#voiceSelector"), selectedVoiceName: $("#selectedVoiceName"), selectedVoiceMeta: $("#selectedVoiceMeta"),
  referenceScore: $("#referenceScore"), referenceLabel: $("#referenceLabel"), referenceDetails: $("#referenceDetails"), improveClone: $("#improveClone"),
  modelSelector: $("#modelSelector"), selectedModelAvatar: $("#selectedModelAvatar"), selectedModelName: $("#selectedModelName"), selectedModelMeta: $("#selectedModelMeta"),
  modelInstallCard: $("#modelInstallCard"), modelInstallTitle: $("#modelInstallTitle"), modelInstallMeta: $("#modelInstallMeta"), installSelectedModel: $("#installSelectedModel"),
  profileButtons: $("#profileButtons"), speed: $("#speed"), speedValue: $("#speedValue"), stability: $("#stability"), style: $("#style"),
  pitch: $("#pitch"), pitchValue: $("#pitchValue"), output: $("#outputFormat"), soundSelect: $("#soundSelect"), previewSound: $("#previewSound"),
  addSound: $("#addSound"), repairSounds: $("#repairSounds"), soundFile: $("#soundFile"), musicVolume: $("#musicVolume"), musicVolumeValue: $("#musicVolumeValue"), musicStatus: $("#musicStatus"),
  speakerBoost: $("#speakerBoost"), mode: $("#mode"), reset: $("#resetSettings"), theme: $("#themeButton"), modelStatus: $("#modelStatus"),
  settingsPanel: $("#settingsPanel"), historyPanel: $("#historyPanel"), tabs: $("#tabs"), historySearch: $("#historySearch"), historyList: $("#historyList"), clearHistory: $("#clearHistory"),
  selectorSheet: $("#selectorSheet"), selectorBack: $("#selectorBack"), selectorTitle: $("#selectorTitle"), selectorSubtitle: $("#selectorSubtitle"),
  voiceSheetView: $("#voiceSheetView"), modelSheetView: $("#modelSheetView"),
  voiceSearch: $("#voiceSearch"), voiceList: $("#voiceList"), addVoice: $("#addVoice"), voiceFile: $("#voiceFile"),
  compatibleModelList: $("#compatibleModelList"), modelSearch: $("#modelSearch"), modelSearchState: $("#modelSearchState"), modelSearchResults: $("#modelSearchResults"),
  transcriptDialog: $("#transcriptDialog"), transcriptForm: $("#transcriptForm"), transcriptInput: $("#transcriptInput"), saveTranscript: $("#saveTranscript"), removeTranscript: $("#removeTranscript"),
  voiceImportDialog: $("#voiceImportDialog"), voiceImportForm: $("#voiceImportForm"), importSummary: $("#importSummary"), importTranscript: $("#importTranscript"), confirmVoiceImport: $("#confirmVoiceImport"),
  tooltip: $("#tooltip"), toast: $("#toast"),
  engineMiniCard: $("#engineMiniCard"), engineMiniTitle: $("#engineMiniTitle"), engineMiniMeta: $("#engineMiniMeta"), manageEngine: $("#manageEngine"),
  engineSetup: $("#engineSetup"), engineSetupClose: $("#engineSetupClose"),
  engineIntroView: $("#engineIntroView"), engineProgressView: $("#engineProgressView"), engineDoneView: $("#engineDoneView"), engineManageView: $("#engineManageView"),
  setupIntroKicker: $("#setupIntroKicker"), setupIntroTitle: $("#engineSetupTitle"), setupIntroBody: $("#setupIntroBody"),
  setupHardwareName: $("#setupHardwareName"), setupHardwareMeta: $("#setupHardwareMeta"), setupRecommended: $("#setupRecommended"),
  engineFlavorList: $("#engineFlavorList"), setupDownloadSize: $("#setupDownloadSize"), installEngineButton: $("#installEngineButton"),
  engineCatalogError: $("#engineCatalogError"), setupProgressKicker: $("#setupProgressKicker"), setupProgressTitle: $("#setupProgressTitle"),
  setupProgressMessage: $("#setupProgressMessage"), setupProgressBar: $("#setupProgressBar"), setupProgressPercent: $("#setupProgressPercent"),
  setupProgressBytes: $("#setupProgressBytes"), setupSteps: $("#setupSteps"), cancelEngineInstall: $("#cancelEngineInstall"),
  setupDoneMeta: $("#setupDoneMeta"), enterStudioButton: $("#enterStudioButton"), manageEngineTitle: $("#manageEngineTitle"),
  manageEngineMeta: $("#manageEngineMeta"), repairEngineButton: $("#repairEngineButton"), uninstallEngineButton: $("#uninstallEngineButton")
};

function esc(v){return String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;")}
function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
function fmtTime(v){if(!Number.isFinite(v)||v<0)return"0:00";const m=Math.floor(v/60),s=Math.floor(v%60);return`${m}:${String(s).padStart(2,"0")}`}
function prettyDate(v){try{return new Intl.DateTimeFormat("es-PE",{dateStyle:"medium",timeStyle:"short"}).format(new Date(v))}catch{return""}}

async function api(path, options={}){
  let r;
  try{
    r=await fetch(`${API}${path}`,{cache:"no-store",...options});
  }catch(networkError){
    if(networkError?.name==="AbortError")throw networkError;
    throw new Error("No se pudo conectar con el motor local. Puede haberse detenido; reinicia Voice Studio AI.");
  }
  if(!r.ok){const b=await r.json().catch(()=>({}));throw new Error(b.detail||b.error||`HTTP ${r.status}`)}
  return r.headers.get("content-type")?.includes("json")?r.json():r;
}
function toast(msg,tone=""){el.toast.textContent=msg;el.toast.dataset.tone=tone;el.toast.classList.add("show");clearTimeout(toast.t);toast.t=setTimeout(()=>el.toast.classList.remove("show"),3200)}

function authorMark(model){
  const author=model?.author||model?.id?.split("/")[0]||"AI";
  return esc(author.slice(0,1).toUpperCase());
}
function avatarHTML(model, cls="model-avatar"){
  const url=model?.avatar_url;
  return `<span class="${cls}">${url?`<img src="${esc(url)}" alt="" loading="lazy">`:""}<span>${authorMark(model)}</span></span>`;
}
function installAvatarFallbacks(root=document){
  root.querySelectorAll(".model-avatar img").forEach(img=>{
    img.addEventListener("error",()=>img.remove(),{once:true});
  });
}

function selectedModel(){
  return state.model || state.models.compatible.find(m=>m.id===state.models.recommended_id) || state.models.compatible[0] || null;
}
function modelInstallState(model){
  if(!model)return "not_installed";
  return model.install_state||(model.installed?"installed":"not_installed");
}
function applyModelInstallStatus(modelId,status){
  const fields={
    installed:Boolean(status.installed),
    install_state:status.state||"not_installed",
    install_message:status.message||"",
    install_error:status.error||null,
    downloaded_bytes:Number(status.downloaded_bytes||0),
    expected_bytes:Number(status.expected_bytes||0)
  };
  state.models.compatible=(state.models.compatible||[]).map(model=>model.id===modelId?{...model,...fields}:model);
  if(state.model?.id===modelId)state.model={...state.model,...fields};
}
function renderModelInstallStatus(){
  const model=selectedModel();
  if(!model){
    el.modelInstallCard.dataset.state="not_installed";
    el.modelInstallTitle.textContent="Selecciona un modelo";
    el.modelInstallMeta.textContent="Elige un modelo compatible para instalarlo.";
    el.installSelectedModel.textContent="Sin modelo";
    el.installSelectedModel.disabled=true;
    return;
  }

  const status=modelInstallState(model);
  el.modelInstallCard.dataset.state=status;
  el.installSelectedModel.classList.toggle("installed",status==="installed");

  if(status==="installed"){
    el.modelInstallTitle.textContent="Modelo instalado";
    el.modelInstallMeta.textContent=`${model.name} · disponible sin conexión`;
    el.installSelectedModel.innerHTML=`${icons.check}<span>Instalado</span>`;
    el.installSelectedModel.disabled=true;
    return;
  }
  if(status==="downloading"){
    const downloaded=Number(model.downloaded_bytes||0);
    const expected=Number(model.expected_bytes||0);
    el.modelInstallTitle.textContent="Instalando modelo…";
    el.modelInstallMeta.textContent=downloaded
      ? `${humanBytes(downloaded)} descargados${expected?` · aprox. ${humanBytes(expected)}`:""}`
      : "Conectando con Hugging Face. La descarga se reanuda si se interrumpe.";
    el.installSelectedModel.innerHTML=`<span class="spinner"></span><span>Instalando</span>`;
    el.installSelectedModel.disabled=true;
    return;
  }
  if(status==="error"){
    el.modelInstallTitle.textContent="Descarga interrumpida";
    el.modelInstallMeta.textContent=model.install_message||"Revisa tu conexión y vuelve a intentarlo.";
    el.installSelectedModel.textContent="Reintentar";
    el.installSelectedModel.disabled=false;
    return;
  }

  el.modelInstallTitle.textContent="Modelo no instalado";
  el.modelInstallMeta.textContent=`${model.disk_gb?`${model.disk_gb} GB aprox. · `:""}se descarga una vez y queda en este equipo`;
  el.installSelectedModel.textContent="Instalar modelo";
  el.installSelectedModel.disabled=false;
}
function selectModel(id){
  const all=[...(state.models.compatible||[]),...(state.models.discovery||[])];
  const found=all.find(m=>m.id===id);
  if(!found) return false;
  if(!found.compatible){
    toast(found.compatibility_note||"Este modelo requiere un adaptador diferente.","error");
    return false;
  }
  state.model=found;
  updateModelUI();
  savePreferences();
  return true;
}
function updateModelUI(){
  const m=selectedModel();
  if(!m){renderModelInstallStatus();updateGenerate();return}
  el.selectedModelName.textContent=m.name;
  el.selectedModelMeta.textContent=`${m.installed?"Instalado":"Sin instalar"} · ${m.recommended?"Recomendado · ":""}${m.disk_gb?`${m.disk_gb} GB`:"local"}`;
  el.selectedModelAvatar.innerHTML=`${m.avatar_url?`<img src="${esc(m.avatar_url)}" alt="">`:""}<span>${authorMark(m)}</span>`;
  installAvatarFallbacks(el.selectedModelAvatar);
  el.bottomMode.textContent=m.name;
  renderModelInstallStatus();
  updateGenerate();
  updateHardwareHint();
}
function renderCompatibleModels(){
  const list=state.models.compatible||[];
  el.compatibleModelList.innerHTML=list.length
    ? list.map((m,i)=>modelRow(m,i,true)).join("")
    : `<div class="empty-list compact"><strong>Cargando modelos…</strong><span>Qwen recomendado aparecerá aquí.</span></div>`;
  installAvatarFallbacks(el.compatibleModelList);
}
function modelRow(m,i,selectable){
  const installState=modelInstallState(m);
  const meta=[
    m.family,
    m.disk_gb?`${m.disk_gb} GB`:null,
    m.license,
  ].filter(Boolean).join(" · ");
  const action=!m.compatible
    ? `<span class="compat-badge adapter">Adaptador</span>`
    : installState==="installed"
      ? `<button class="model-row-action installed" type="button" disabled>${icons.check}<span>Instalado</span></button>`
      : installState==="downloading"
        ? `<button class="model-row-action" type="button" disabled><span class="spinner"></span><span>Instalando</span></button>`
        : `<button class="model-row-action" type="button" data-install-model="${esc(m.id)}">${installState==="error"?"Reintentar":"Instalar"}</button>`;
  return `<div class="model-row ${state.model?.id===m.id?"selected":""}" data-install-state="${esc(installState)}" style="--i:${i}">
    ${avatarHTML(m)}
    <button class="model-main" data-model="${esc(m.id)}" ${selectable&&m.compatible?"":"data-disabled='true'"}>
      <span class="model-title-line"><strong>${esc(m.name)}</strong>${m.recommended?`<em>Recomendado</em>`:""}</span>
      <small>${esc(meta||m.author||"Hugging Face")}</small>
      ${m.compatibility_note?`<p>${esc(m.compatibility_note)}</p>`:""}
    </button>
    ${action}
  </div>`;
}
function wireModelRows(root){
  installAvatarFallbacks(root);
}
async function searchModels(){
  const q=el.modelSearch.value.trim();
  clearTimeout(state.modelSearchTimer);
  if(q.length<2){el.modelSearchResults.innerHTML="";el.modelSearchState.textContent="Escribe al menos 2 caracteres.";return}
  el.modelSearchState.textContent="Buscando en Hugging Face…";
  state.modelSearchTimer=setTimeout(async()=>{
    try{
      const data=await api(`/api/models/search?q=${encodeURIComponent(q)}&limit=18`);
      const list=data.results||[];
      el.modelSearchState.textContent=list.length?`${list.length} resultados · la ejecución depende del adaptador.`:"No se encontraron modelos TTS.";
      el.modelSearchResults.innerHTML=list.map((m,i)=>modelRow(m,i,true)).join("");
      wireModelRows(el.modelSearchResults);
    }catch(e){el.modelSearchState.textContent="Sin conexión con Hugging Face. Los modelos compatibles locales siguen disponibles."}
  },300);
}

async function refreshModelsOnly(){
  const selectedId=state.model?.id;
  const models=await api("/api/models");
  state.models=models;
  state.model=models.compatible.find(model=>model.id===selectedId)
    ||models.compatible.find(model=>model.id===models.recommended_id)
    ||models.compatible[0]
    ||null;
  renderCompatibleModels();
  updateModelUI();
}
function stopModelInstallPolling(){
  clearInterval(state.modelInstallTimer);
  state.modelInstallTimer=null;
  state.modelInstallId=null;
}
async function pollModelInstall(modelId){
  stopModelInstallPolling();
  state.modelInstallId=modelId;
  let checking=false;
  const check=async()=>{
    if(checking)return;
    checking=true;
    try{
      const status=await api(`/api/models/install/status?model_id=${encodeURIComponent(modelId)}`);
      applyModelInstallStatus(modelId,status);
      renderCompatibleModels();
      updateModelUI();
      if(status.state==="installed"){
        stopModelInstallPolling();
        await refreshModelsOnly();
        toast("Modelo instalado y listo para generar.","success");
      }else if(status.state==="error"){
        stopModelInstallPolling();
        toast(status.message||"No se pudo instalar el modelo.","error");
      }
    }catch{
      if(state.modelInstallId===modelId){
        el.modelInstallMeta.textContent="Esperando al motor local para continuar la comprobación…";
      }
    }finally{checking=false}
  };
  await check();
  if(state.modelInstallId===modelId)state.modelInstallTimer=setInterval(check,1200);
}
async function installModel(modelId){
  const model=(state.models.compatible||[]).find(item=>item.id===modelId);
  if(!model||!model.compatible)return toast("Este modelo necesita otro adaptador.","error");
  if(model.installed)return toast("El modelo ya está instalado.","success");

  applyModelInstallStatus(modelId,{
    state:"downloading",
    installed:false,
    message:"Iniciando descarga desde Hugging Face.",
    downloaded_bytes:model.downloaded_bytes||0,
    expected_bytes:model.expected_bytes||Math.round(Number(model.disk_gb||0)*(1024**3))
  });
  renderCompatibleModels();
  updateModelUI();

  try{
    const status=await api("/api/models/install",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({model_id:modelId})
    });
    applyModelInstallStatus(modelId,status);
    renderCompatibleModels();
    updateModelUI();
    if(status.state==="installed"){
      await refreshModelsOnly();
      toast("El modelo ya estaba instalado y fue detectado.","success");
      return;
    }
    await pollModelInstall(modelId);
  }catch(error){
    applyModelInstallStatus(modelId,{
      state:"error",
      installed:false,
      message:error.message||"No se pudo iniciar la descarga.",
      error:error.message
    });
    renderCompatibleModels();
    updateModelUI();
    toast(error.message||"No se pudo instalar el modelo.","error");
  }
}

function voiceQualityClass(score){return score>=85?"excellent":score>=70?"good":score>=50?"fair":"poor"}
function updateReference(){
  const v=state.voice;
  el.improveClone.disabled=!v;
  if(!v){
    el.referenceScore.className="reference-score";el.referenceScore.innerHTML="<strong>—</strong><small>/100</small>";
    el.referenceLabel.textContent="Selecciona una voz";el.referenceDetails.textContent="Duración, nivel, clipping y transcripción.";return
  }
  const score=Number(v.quality_score||0), cls=voiceQualityClass(score);
  el.referenceScore.className=`reference-score ${cls}`;el.referenceScore.innerHTML=`<strong>${score}</strong><small>/100</small>`;
  el.referenceLabel.textContent=v.quality_label||"Analizada";
  const dur=v.duration?`${Number(v.duration).toFixed(1)} s`:"duración desconocida";
  el.referenceDetails.textContent=`${dur} · ${v.has_transcript?"ICL":"X-vector"} · ${v.prepared?"24 kHz mono preparado":"original"}`;
}
function updateVoiceUI(){
  if(!state.voice){
    el.selectedVoiceName.textContent="Selecciona una voz";el.selectedVoiceMeta.textContent="Mis voces";
    el.bottomVoice.textContent="Sin voz seleccionada";el.icl.textContent="Selecciona una voz";updateReference();return updateGenerate()
  }
  el.selectedVoiceName.textContent=state.voice.name;
  el.selectedVoiceMeta.textContent=state.voice.has_transcript?"ICL · audio + transcripción":"X-vector · sin transcripción";
  el.bottomVoice.textContent=state.voice.name;
  el.icl.textContent=state.voice.has_transcript?"ICL activo · mayor fidelidad":"Solo X-vector · menor fidelidad";
  updateReference();updateGenerate();
}
function renderVoices(filter=""){
  const q=filter.toLowerCase().trim();
  const list=state.voices.filter(v=>!q||`${v.name} ${v.filename}`.toLowerCase().includes(q));
  el.voiceList.innerHTML=list.length?list.map((v,i)=>`
    <div class="voice-row ${state.voice?.id===v.id?"selected":""}" style="--i:${i}">
      <span class="voice-avatar">${icons.wave}</span>
      <button class="voice-main" data-select-voice="${esc(v.id)}">
        <strong>${esc(v.name)}</strong><small>${v.has_transcript?"ICL · mayor fidelidad":"X-vector · agregar transcripción"}</small>
      </button>
      <span class="quality-pill ${voiceQualityClass(v.quality_score)}">${Math.round(v.quality_score||0)}</span>
      <button class="voice-preview pressable" data-preview-voice="${esc(v.id)}">${icons.play}</button>
    </div>`).join(""):`<div class="empty-list"><strong>No se encontraron voces</strong><span>Agrega un audio para comenzar.</span></div>`;
}
function updateMusicUI(){
  const selected=state.sounds.find(x=>x.id===state.selectedSoundId);
  el.soundSelect.value=selected ? selected.id : "";
  el.previewSound.disabled=!selected;

  const hasResult=!!state.result?.history?.id;
  const appliedId=state.result?.music_id||"";
  el.applyMusic.disabled=!hasResult||!selected||selected.id===appliedId||state.musicBusy;
  el.removeMusic.disabled=!hasResult||!appliedId||state.musicBusy;
  el.musicButton.classList.toggle("has-music",!!appliedId);

  if(!hasResult){
    el.musicStatus.textContent="Genera una locución primero para poder agregarle música.";
  }else if(selected){
    el.musicStatus.innerHTML=selected.id===appliedId
      ? `<strong>${esc(selected.name)}</strong> ya está aplicada a este resultado.`
      : `<strong>${esc(selected.name)}</strong> · ${el.musicVolume.value}% · pulsa "Aplicar música" para mezclarla.`;
  }else if(appliedId){
    el.musicStatus.innerHTML=`<strong>${esc(state.result.music_name||"Música")}</strong> aplicada. Elige otra pista o quítala.`;
  }else{
    el.musicStatus.textContent="Sin música. Elige una pista y aplícala a esta locución ya generada.";
  }
}

async function updateResultMusic(soundId){
  const historyId=state.result?.history?.id;
  if(!historyId||state.musicBusy)return;
  state.musicBusy=true;updateMusicUI();
  try{
    const updated=await api(`/api/history/${encodeURIComponent(historyId)}/music`,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sound_id:soundId||null,music_volume:Number(el.musicVolume.value)/100})
    });
    state.result={...state.result,history:updated,music_id:updated.music_id,music_name:updated.music_name,url:updated.url,filename:updated.filename};
    await setResultAudio(`${API}${updated.url}`,updated.filename,state.voice?.name);
    await refreshData();
    toast(soundId?`Música aplicada: ${updated.music_name}`:"Música quitada.","success");
  }catch(e){
    toast(e.message,"error");
  }finally{
    state.musicBusy=false;updateMusicUI();
  }
}

function renderSounds(){
  const options=state.sounds.map(x=>`<option value="${esc(x.id)}" ${x.valid===false?"disabled":""}>${esc(x.name)}${x.valid===false?" · ARCHIVO INVÁLIDO":""}</option>`).join("");
  el.soundSelect.innerHTML=`<option value="">Sin música</option>${options}`;

  const selected=state.sounds.find(x=>x.id===state.selectedSoundId);
  if(!selected || selected.valid===false) state.selectedSoundId="";
  updateMusicUI();
}
function renderHistory(){
  const q=el.historySearch.value.trim().toLowerCase();
  const list=state.history.filter(h=>!q||`${h.title} ${h.voice_name} ${h.model_name||""}`.toLowerCase().includes(q));
  el.historyList.innerHTML=list.length?list.map((h,i)=>`
    <button class="history-item pressable" data-history-url="${esc(h.url)}" data-history-file="${esc(h.filename)}" data-history-voice="${esc(h.voice_name)}" style="--i:${i}">
      <span class="history-play">${icons.play}</span>
      <span class="history-copy"><strong>${esc(h.title)}</strong><small>${esc(h.voice_name)} · ${esc(h.model_name||"Qwen")}${h.music_name?` · ♪ ${esc(h.music_name)}`:""} · ${prettyDate(h.created_at)}</small></span>
      <span class="history-format">${esc((h.filename||"wav").split(".").pop().toUpperCase())}</span>
    </button>`).join(""):`<div class="empty-list"><strong>Aún no hay historial</strong><span>Las locuciones aparecerán aquí.</span></div>`;
  $$("[data-history-url]").forEach(b=>b.onclick=()=>setResultAudio(`${API}${b.dataset.historyUrl}`,b.dataset.historyFile,b.dataset.historyVoice));
}

function triggerFor(kind){
  if(kind==="voice") return el.voiceSelector;
  if(kind==="model") return el.modelSelector;
  return null;
}

function setSelectorView(kind){
  const voiceActive=kind==="voice";
  const modelActive=kind==="model";

  el.voiceSheetView.hidden=!voiceActive;
  el.modelSheetView.hidden=!modelActive;

  el.voiceSheetView.classList.toggle("active",voiceActive);
  el.modelSheetView.classList.toggle("active",modelActive);

  if(voiceActive){
    el.selectorTitle.textContent="Seleccionar voz";
    el.selectorSubtitle.textContent="Referencias locales";
    renderVoices(el.voiceSearch.value);
  }else{
    el.selectorTitle.textContent="Seleccionar modelo";
    el.selectorSubtitle.textContent="Hugging Face · Qwen recomendado";
    renderCompatibleModels();
  }
}

function closeAllSheets({focus=false}={}){
  const previous=state.activeSheet;
  state.activeSheet=null;

  el.selectorSheet.classList.remove("open");
  el.selectorSheet.setAttribute("aria-hidden","true");
  el.voiceSheetView.hidden=true;
  el.modelSheetView.hidden=true;
  el.voiceSheetView.classList.remove("active");
  el.modelSheetView.classList.remove("active");

  document.querySelector(".side-pane")?.removeAttribute("data-sheet");
  stopPreview();

  if(focus && previous){
    requestAnimationFrame(()=>triggerFor(previous)?.focus());
  }
}

function openSheet(kind){
  if(kind!=="voice" && kind!=="model") return;

  state.activeSheet=kind;
  setSelectorView(kind);

  document.querySelector(".side-pane")?.setAttribute("data-sheet",kind);
  el.selectorSheet.setAttribute("aria-hidden","false");
  el.selectorSheet.classList.add("open");

  requestAnimationFrame(()=>{
    (kind==="voice" ? el.voiceSearch : el.modelSearch)?.focus();
  });
}

function closeSheet(kind=state.activeSheet,{focus=true}={}){
  const previous=kind || state.activeSheet;
  closeAllSheets();
  if(focus && previous){
    requestAnimationFrame(()=>triggerFor(previous)?.focus());
  }
}

function stopPreview(){if(!state.preview)return;state.preview.audio.pause();state.preview.button.innerHTML=icons.play;state.preview=null}
function preview(url,button){
  if(state.preview?.url===url&&!state.preview.audio.paused)return stopPreview();
  stopPreview();const a=new Audio(url);state.preview={audio:a,button,url};button.innerHTML=icons.pause;
  a.onended=stopPreview;a.onerror=stopPreview;a.play().catch(stopPreview);
}

const PROFILE_VALUES={
  faithful:{speed:1,stability:82,style:0,pitch:0,boost:false},
  natural:{speed:1,stability:55,style:0,pitch:0,boost:true},
  spot:{speed:1.04,stability:45,style:20,pitch:0,boost:true}
};
function applyProfile(name,announce=true){
  const p=PROFILE_VALUES[name];if(!p)return;state.profile=name;
  el.speed.value=p.speed;el.stability.value=p.stability;el.style.value=p.style;el.pitch.value=p.pitch;
  el.speakerBoost.classList.toggle("on",p.boost);el.speakerBoost.setAttribute("aria-pressed",String(p.boost));
  $$("#profileButtons button").forEach(b=>b.classList.toggle("active",b.dataset.profile===name));
  syncLabels();savePreferences();if(announce)toast(`Perfil ${name==="faithful"?"Fiel":name==="spot"?"Spot":"Natural"} aplicado.`);
}
function estimateDuration(){
  const text=el.script.value.trim();if(!text){el.duration.textContent="≈ 0 s";return}
  const words=text.split(/\s+/).filter(Boolean).length,speed=Math.max(.8,Number(el.speed.value)||1),seconds=Math.max(1,Math.round(words/(2.65*speed)));
  el.duration.textContent=`≈ ${seconds} s`;el.duration.classList.toggle("target",seconds>=9&&seconds<=11);
}
function syncLabels(){el.speedValue.textContent=`${Number(el.speed.value).toFixed(2)}×`;el.pitchValue.textContent=`${Number(el.pitch.value).toFixed(1)} st`;el.musicVolumeValue.textContent=`${el.musicVolume.value}%`;estimateDuration()}
function updateGenerate(){
  const model=selectedModel();
  el.generate.disabled=!(state.voice&&model?.compatible&&model.installed&&el.script.value.trim())||state.busy;
  if(!state.busy)el.generateText.textContent=model&&!model.installed?"Instala el modelo":state.result?"Regenerar":"Generar";
}
function savePreferences(){
  try{
    localStorage.setItem("vsa-settings",JSON.stringify({
      model_id:selectedModel()?.id||DEFAULT_MODEL_ID,profile:state.profile,speed:el.speed.value,stability:el.stability.value,style:el.style.value,
      pitch:el.pitch.value,output:el.output.value,mode:el.mode.value,musicVolume:el.musicVolume.value,boost:el.speakerBoost.classList.contains("on")
    }));
  }catch{
    // Storage may be unavailable in restricted WebViews; navigation must still work.
  }
}
function loadPreferences(){
  try{
    const p=JSON.parse(localStorage.getItem("vsa-settings")||"{}");state.profile=p.profile||"natural";
    const base=PROFILE_VALUES[state.profile]||PROFILE_VALUES.natural;
    el.speed.value=p.speed??base.speed;el.stability.value=p.stability??base.stability;el.style.value=p.style??base.style;el.pitch.value=p.pitch??base.pitch;
    el.output.value=p.output||"wav";el.mode.value=p.mode||"auto";el.musicVolume.value=p.musicVolume||18;state.selectedSoundId="";
    el.speakerBoost.classList.toggle("on",p.boost??base.boost);el.speakerBoost.setAttribute("aria-pressed",String(p.boost??base.boost));
    $$("#profileButtons button").forEach(b=>b.classList.toggle("active",b.dataset.profile===state.profile));
    const candidate=state.models.compatible.find(m=>m.id===(p.model_id||DEFAULT_MODEL_ID));
    state.model=candidate||state.models.compatible.find(m=>m.id===state.models.recommended_id)||state.models.compatible[0]||null;
  }catch{
    state.profile="natural";state.model=state.models.compatible.find(m=>m.id===state.models.recommended_id)||state.models.compatible[0]||null;
  }
  syncLabels();updateModelUI();
}
function settingsPayload(){
  return {
    text:el.script.value.trim(),voice_id:state.voice.id,model_id:selectedModel().id,language:"Spanish",mode:el.mode.value,profile:state.profile,
    speed:Number(el.speed.value),stability:Number(el.stability.value)/100,style_exaggeration:Number(el.style.value)/100,
    pitch_semitones:Number(el.pitch.value),speaker_boost:el.speakerBoost.classList.contains("on"),output_format:el.output.value
  }
}

function setBusy(on){
  state.busy=on;updateGenerate();el.generate.classList.toggle("generating",on);el.orb.classList.toggle("thinking",on);
  el.cancelGeneration.hidden=!on;
  if(on){
    el.strip.classList.add("visible");el.strip.classList.remove("success","error");el.generateIcon.innerHTML=`<span class="spinner"></span>`;el.generateText.textContent="Generando";
  }else{
    el.generateIcon.innerHTML=icons.spark;updateGenerate();
  }
}
function hideStrip(delay=1300){clearTimeout(hideStrip.t);hideStrip.t=setTimeout(()=>el.strip.classList.remove("visible","success","error"),delay)}
function stageFor(st){
  const map={
    checking:["Comprobando hardware","Seleccionando el mejor modo para este modelo."],
    loading_model:["Cargando modelo","Leyendo el modelo instalado desde este equipo."],
    preparing_voice:["Preparando referencia","Leyendo identidad vocal y contexto ICL."],
    generating:["Generando locución","Sintetizando la voz localmente."],
    postprocessing:["Ajustando audio","Aplicando velocidad, tono y realce local."],
    mixing:["Mezclando música","Aplicando el fondo seleccionado al archivo final."],
    saving:["Guardando resultado","Escribiendo el archivo final."],
    done:["Locución lista","El reproductor ya está disponible."]
  };
  const [a,b]=map[st.stage]||["Procesando",st.message||"Trabajando localmente."];el.stripTitle.textContent=a;el.stripText.textContent=b;el.stripEngine.textContent=String(st.backend||"LOCAL").toUpperCase()
}
function pollStatus(){
  clearInterval(state.statusTimer);
  let misses=0;
  state.statusTimer=setInterval(async()=>{
    try{
      stageFor(await api("/api/status"));
      misses=0;
    }catch{
      // A few consecutive misses during a long generation are normal jitter;
      // beyond that, the engine likely stopped responding — say so instead
      // of leaving a stale "Generando…" message with no explanation.
      if(++misses===4){
        el.stripTitle.textContent="El motor no responde";
        el.stripText.textContent="Puede haberse detenido. Esperando respuesta…";
      }
    }
  },650);
}

async function generate(){
  if(!state.voice||!selectedModel()?.compatible||!el.script.value.trim())return;
  if(!selectedModel()?.installed){toast("Instala el modelo seleccionado antes de generar.","error");return}
  stopPreview();setBusy(true);pollStatus();
  const requestId=crypto.randomUUID();
  state.generationRequestId=requestId;
  state.generationController=new AbortController();
  try{
    const result=await api("/api/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...settingsPayload(),request_id:requestId}),signal:state.generationController.signal});
    const url=`${API}${result.url}`,name=result.filename;
    state.result=result;state.selectedSoundId="";
    await setResultAudio(url,name,state.voice.name);
    updateMusicUI();
    el.strip.classList.add("success");
    el.stripTitle.textContent="Locución lista";
    el.stripText.textContent=`${result.model_name} · ${result.backend.toUpperCase()} · ${result.used_transcript?"ICL":"X-vector"}`;
    await refreshData();toast("Locución generada. Ahora puedes agregarle música desde el reproductor.","success");hideStrip(1450);
  }catch(e){
    if(e.name==="AbortError"){
      el.strip.classList.add("visible");el.strip.classList.remove("success","error");
      el.stripTitle.textContent="Cancelado";el.stripText.textContent="Se canceló la generación.";
      hideStrip(1800);
    }else{
      el.strip.classList.add("visible","error");el.stripTitle.textContent="No se pudo generar";el.stripText.textContent=e.message;toast(e.message,"error");hideStrip(4300);
    }
  }finally{
    clearInterval(state.statusTimer);state.statusTimer=null;setBusy(false);
    state.generationController=null;state.generationRequestId=null;
  }
}
function cancelGeneration(){
  const requestId=state.generationRequestId;
  if(!requestId)return;
  state.generationController?.abort();
  api("/api/generate/cancel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request_id:requestId})}).catch(()=>{});
}

async function setResultAudio(url,filename,voiceName){
  state.result={...(state.result||{}),url,filename};
  el.audio.src=url;el.download.href=url;el.download.download=filename||"locucion.wav";el.download.classList.remove("disabled");
  el.bottomVoice.textContent=voiceName||state.voice?.name||"Resultado";
  el.player.classList.add("visible");el.transport.classList.add("has-result");
  await buildWaveform(url);
  try{await el.audio.play();el.playerPlay.innerHTML=icons.pause}catch{}
}
async function buildWaveform(url){
  if(state.waveformUrl===url&&state.waveform.length){drawWaveform();return}
  try{
    const arr=await fetch(url).then(r=>r.arrayBuffer()),Ctx=window.AudioContext||window.webkitAudioContext,ctx=new Ctx(),buf=await ctx.decodeAudioData(arr.slice(0));
    const data=buf.getChannelData(0),bars=112,block=Math.max(1,Math.floor(data.length/bars)),peaks=[];
    for(let i=0;i<bars;i++){let peak=0,start=i*block,end=Math.min(data.length,start+block);for(let j=start;j<end;j+=Math.max(1,Math.floor(block/80)))peak=Math.max(peak,Math.abs(data[j]));peaks.push(Math.max(.05,peak))}
    state.waveform=peaks;state.waveformUrl=url;await ctx.close();drawWaveform()
  }catch{state.waveform=Array.from({length:112},(_,i)=>.25+.12*Math.sin(i*.7));drawWaveform()}
}
function drawWaveform(){
  const c=el.waveform,rect=c.getBoundingClientRect(),dpr=window.devicePixelRatio||1,w=Math.max(1,Math.floor(rect.width*dpr)),h=Math.max(1,Math.floor(rect.height*dpr));
  if(c.width!==w||c.height!==h){c.width=w;c.height=h}
  const ctx=c.getContext("2d"),styles=getComputedStyle(document.documentElement),muted=styles.getPropertyValue("--wave-muted").trim()||"#737a70",active=styles.getPropertyValue("--accent").trim()||"#315f52";
  ctx.clearRect(0,0,w,h);const arr=state.waveform.length?state.waveform:Array(112).fill(.15),gap=2*dpr,bw=Math.max(1.4*dpr,(w-gap*(arr.length-1))/arr.length),progress=el.audio.duration?el.audio.currentTime/el.audio.duration:0;
  arr.forEach((p,i)=>{const bh=Math.max(3*dpr,p*h*.88),x=i*(bw+gap),y=(h-bh)/2;ctx.fillStyle=(i/(arr.length-1))<=progress?active:muted;ctx.globalAlpha=(i/(arr.length-1))<=progress?1:.42;ctx.beginPath();ctx.roundRect(x,y,bw,bh,bw/2);ctx.fill()});ctx.globalAlpha=1;
}
function seekFromEvent(e){
  if(!el.audio.duration)return;const r=el.waveform.getBoundingClientRect(),ratio=clamp((e.clientX-r.left)/r.width,0,1);el.audio.currentTime=ratio*el.audio.duration;drawWaveform()
}
function wirePlayer(){
  el.playerPlay.onclick=async()=>{if(!el.audio.src)return;if(el.audio.paused){await el.audio.play();el.playerPlay.innerHTML=icons.pause}else{el.audio.pause();el.playerPlay.innerHTML=icons.play}};
  el.audio.addEventListener("play",()=>el.playerPlay.innerHTML=icons.pause);el.audio.addEventListener("pause",()=>el.playerPlay.innerHTML=icons.play);
  el.audio.addEventListener("timeupdate",()=>{el.playerCurrent.textContent=fmtTime(el.audio.currentTime);drawWaveform()});
  el.audio.addEventListener("loadedmetadata",()=>{el.playerDuration.textContent=fmtTime(el.audio.duration);drawWaveform()});
  el.audio.addEventListener("ended",()=>el.playerPlay.innerHTML=icons.play);
  el.waveform.addEventListener("pointerdown",e=>{state.seeking=true;el.waveform.setPointerCapture(e.pointerId);seekFromEvent(e)});
  el.waveform.addEventListener("pointermove",e=>{if(state.seeking)seekFromEvent(e)});
  el.waveform.addEventListener("pointerup",()=>state.seeking=false);el.waveform.addEventListener("pointercancel",()=>state.seeking=false);
  el.volumeButton.onclick=()=>el.volumePopover.classList.toggle("open");
  el.musicButton.onclick=()=>el.musicPopover.classList.toggle("open");
  el.playerVolume.oninput=()=>el.audio.volume=Number(el.playerVolume.value);
  window.addEventListener("resize",drawWaveform);
}

async function refreshData(){
  const [voices,sounds,history,system,models]=await Promise.all([api("/api/voices"),api("/api/sounds"),api("/api/history"),api("/api/system"),api("/api/models")]);
  state.voices=voices;state.sounds=sounds;state.history=history;state.models=models;
  if(state.voice)state.voice=voices.find(v=>v.id===state.voice.id)||null;
  renderVoices(el.voiceSearch.value);renderSounds();renderHistory();renderCompatibleModels();
  if(!state.model)loadPreferences();else{
    const m=models.compatible.find(x=>x.id===state.model.id);state.model=m||models.compatible.find(x=>x.id===models.recommended_id)||models.compatible[0]||null;updateModelUI()
  }
  state.system=system;updateHardwareHint();updateVoiceUI();
}
function updateHardwareHint(){
  const sys=state.system;if(!sys)return;const m=selectedModel(),need=Number(m?.gpu_vram_recommended_gb||5.5),vram=Number(sys.vram_gb||0),auto=sys.cuda_available&&vram>=need?"CUDA":"CPU";
  el.hardware.textContent=sys.cuda_available?`${sys.gpu_name} · ${vram.toFixed(1)} GB · Auto→${auto}`:"CPU · modo local";
}
function switchTab(tab){
  closeAllSheets();
  $$(".tabs button").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
  el.tabs.dataset.active=tab;
  el.settingsPanel.classList.toggle("active",tab==="settings");
  el.historyPanel.classList.toggle("active",tab==="history");
  if(tab==="settings") requestAnimationFrame(()=>el.settingsPanel.scrollTop=0);
}

async function saveTranscript(text){
  if(!state.voice)return;await api(`/api/voices/${encodeURIComponent(state.voice.id)}/transcript`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({transcript:text})});await refreshData();state.voice=state.voices.find(v=>v.id===state.voice?.id)||state.voice;updateVoiceUI()
}
function openTranscript(){if(!state.voice)return toast("Primero selecciona una voz.");el.transcriptInput.value=state.voice.transcript||"";el.transcriptDialog.showModal();setTimeout(()=>el.transcriptInput.focus(),60)}
function fileDuration(file){return new Promise(resolve=>{const a=document.createElement("audio"),u=URL.createObjectURL(file);a.preload="metadata";a.onloadedmetadata=()=>{const d=a.duration;URL.revokeObjectURL(u);resolve(Number.isFinite(d)?d:null)};a.onerror=()=>{URL.revokeObjectURL(u);resolve(null)};a.src=u})}
async function prepareImport(file){
  state.pendingVoiceFile=file;const d=await fileDuration(file),note=d==null?"No se pudo leer duración":d<3?"Muy corto para Qwen":d<=8?"Válido; una referencia más rica puede ayudar":d<=25?"Rango recomendado":d<=35?"Utilizable; revisa que todo sea consistente":"Referencia larga; usa solo un tramo limpio si la voz cambia";
  el.importSummary.innerHTML=`<strong>${esc(file.name)}</strong><span>${d?`${d.toFixed(1)} s · `:""}${note}</span>`;el.importTranscript.value="";el.voiceImportDialog.showModal()
}
async function importVoice(file,transcript){
  const f=new FormData();f.append("file",file);f.append("transcript",transcript||"");const r=await fetch(`${API}/api/voices/import`,{method:"POST",body:f}),data=await r.json();if(!r.ok)throw new Error(data.detail||"No se pudo importar");
  await refreshData();state.voice=state.voices.find(v=>v.id===data.id)||null;updateVoiceUI();return data
}
async function importSound(file){
  const f=new FormData();
  f.append("file",file);
  const r=await fetch(`${API}/api/sounds/import`,{method:"POST",body:f});
  const data=await r.json();
  if(!r.ok)throw new Error(data.detail||"No se pudo importar");
  state.selectedSoundId=data.id;
  await refreshData();
  state.selectedSoundId=data.id;
  renderSounds();
  savePreferences();
  return data;
}
function toggle(btn){btn.classList.toggle("on");btn.setAttribute("aria-pressed",String(btn.classList.contains("on")))}


function isDesktop(){return Boolean(window.__TAURI_INTERNALS__)}
let tauriInvokeFn=null;
let tauriListenFn=null;
let engineUnlisten=null;
let engineCrashUnlisten=null;

async function tauriInvoke(command,args={}){
  if(!isDesktop())return null;
  if(!tauriInvokeFn){
    const core=await import("@tauri-apps/api/core");
    tauriInvokeFn=core.invoke;
  }
  return tauriInvokeFn(command,args);
}
function humanBytes(bytes){
  const n=Number(bytes||0);
  if(!Number.isFinite(n)||n<=0)return "—";
  const units=["B","KB","MB","GB","TB"];
  let value=n,index=0;
  while(value>=1024&&index<units.length-1){value/=1024;index++}
  return `${value>=100||index===0?value.toFixed(0):value>=10?value.toFixed(1):value.toFixed(2)} ${units[index]}`;
}
function engineViews(active){
  [el.engineIntroView,el.engineProgressView,el.engineDoneView,el.engineManageView].forEach(view=>view.classList.toggle("active",view.id===active));
}
function openEngineSetup(view="engineIntroView",closable=false){
  engineViews(view);
  el.engineSetup.classList.add("open");
  el.engineSetup.setAttribute("aria-hidden","false");
  el.engineSetupClose.hidden=!closable;
  document.documentElement.classList.add("engine-modal-open");
}
function closeEngineSetup(){
  if(state.engine.installing)return;
  el.engineSetup.classList.remove("open");
  el.engineSetup.setAttribute("aria-hidden","true");
  document.documentElement.classList.remove("engine-modal-open");
}
function updateEngineMini(){
  const s=state.engine.status;
  if(!s){
    el.engineMiniTitle.textContent="Comprobando…";
    el.engineMiniMeta.textContent="Python y PyTorch privados de Voice Studio AI";
    return;
  }
  if(s.installed){
    const flavor=s.flavor==="nvidia"?"NVIDIA":s.flavor==="cpu"?"CPU":s.flavor||"Local";
    el.engineMiniTitle.textContent=`Motor ${flavor} · ${s.version||"instalado"}`;
    el.engineMiniMeta.textContent=`${humanBytes(s.installed_bytes)} · ${s.running?"Activo":"Listo"}`;
  }else{
    el.engineMiniTitle.textContent="Motor no instalado";
    el.engineMiniMeta.textContent="Se prepara visualmente al primer inicio";
  }
}
function updateHardwareSetup(hardware,recommended){
  state.engine.hardware=hardware;
  if(hardware?.nvidia_available){
    el.setupHardwareName.textContent=hardware.gpu_name||"NVIDIA detectada";
    const bits=[];
    if(hardware.vram_gb)bits.push(`${Number(hardware.vram_gb).toFixed(1)} GB VRAM`);
    if(hardware.driver_version)bits.push(`Driver ${hardware.driver_version}`);
    el.setupHardwareMeta.textContent=bits.join(" · ")||"Aceleración NVIDIA disponible";
  }else{
    el.setupHardwareName.textContent="Procesamiento por CPU";
    el.setupHardwareMeta.textContent="No se detectó una GPU NVIDIA compatible.";
  }
  el.setupRecommended.textContent=(recommended||"cpu").toUpperCase()+" · RECOMENDADO";
}
function enginePackageFor(flavor){
  return state.engine.catalog?.manifest?.engines?.find(item=>item.flavor===flavor)||null;
}
function versionIsOlder(current,required){
  const parse=value=>String(value||"0").split(".").map(part=>Number.parseInt(part,10)||0);
  const left=parse(current),right=parse(required),length=Math.max(left.length,right.length);
  for(let index=0;index<length;index++){
    const a=left[index]||0,b=right[index]||0;
    if(a!==b)return a<b;
  }
  return false;
}
function configureEngineIntro(mode="install"){
  const updating=mode==="update";
  el.setupIntroKicker.textContent=updating?"ACTUALIZACIÓN REQUERIDA":"PRIMER INICIO";
  el.setupIntroTitle.textContent=updating?"Actualicemos el motor local.":"Preparamos el estudio por ti.";
  el.setupIntroBody.textContent=updating
    ? `La versión ${REQUIRED_ENGINE_VERSION} añade instalación y detección de modelos sin abrir terminales. Tus voces y modelos guardados se conservarán.`
    : "Voice Studio AI descargará su motor de voz de forma segura. No necesitas instalar Python, PyTorch ni abrir una terminal.";
  el.installEngineButton.textContent=updating?"Actualizar motor":"Preparar Voice Studio AI";
}
function selectEngineFlavor(flavor){
  if(state.engine.installing)return;
  if(!enginePackageFor(flavor))return;
  state.engine.selectedFlavor=flavor;
  el.engineFlavorList.querySelectorAll("[data-engine-flavor]").forEach(card=>{
    card.classList.toggle("selected",card.dataset.engineFlavor===flavor);
    card.setAttribute("aria-checked",String(card.dataset.engineFlavor===flavor));
  });
  const pack=enginePackageFor(flavor);
  el.setupDownloadSize.textContent=pack?.download_bytes?humanBytes(pack.download_bytes):"Según el paquete";
  el.installEngineButton.disabled=!pack;
}
function renderEngineFlavors(){
  const engines=state.engine.catalog?.manifest?.engines||[];
  if(!engines.length){
    el.engineFlavorList.innerHTML=`<p class="engine-empty">No hay motores publicados todavía.</p>`;
    el.installEngineButton.disabled=true;
    return;
  }
  const recommended=state.engine.catalog.recommended_flavor;
  el.engineFlavorList.innerHTML=engines.map(pack=>{
    const gpu=pack.flavor==="nvidia";
    const rec=pack.flavor===recommended;
    return `<button type="button" class="engine-flavor-card pressable ${rec?"recommended":""}" data-engine-flavor="${esc(pack.flavor)}" role="radio" aria-checked="false">
      <span class="engine-flavor-icon">${gpu?icons.spark:icons.cpu}</span>
      <span class="engine-flavor-copy">
        <span><strong>${esc(pack.label|| (gpu?"Motor NVIDIA":"Motor CPU"))}</strong>${rec?`<em>RECOMENDADO</em>`:""}</span>
        <small>${esc(pack.description|| (gpu?"Aceleración CUDA para equipos NVIDIA.":"Compatibilidad amplia sin depender de NVIDIA."))}</small>
        <b>${pack.download_bytes?`${humanBytes(pack.download_bytes)} de descarga`:"Tamaño según publicación"}${pack.installed_bytes?` · ${humanBytes(pack.installed_bytes)} instalado`:""}</b>
      </span>
      <span class="engine-radio"><i></i></span>
    </button>`;
  }).join("");
  el.engineFlavorList.querySelectorAll("[data-engine-flavor]").forEach(card=>card.onclick=()=>selectEngineFlavor(card.dataset.engineFlavor));
  selectEngineFlavor(recommended&&enginePackageFor(recommended)?recommended:engines[0].flavor);
}
async function loadEngineCatalog({showErrors=true}={}){
  el.engineCatalogError.hidden=true;
  el.installEngineButton.disabled=true;
  try{
    const catalog=await tauriInvoke("engine_catalog");
    state.engine.catalog=catalog;
    state.engine.status=catalog.status;
    updateEngineMini();
    updateHardwareSetup(catalog.hardware,catalog.recommended_flavor);
    renderEngineFlavors();
    return catalog;
  }catch(error){
    if(showErrors){
      el.engineCatalogError.hidden=false;
      el.engineCatalogError.innerHTML=`No pudimos consultar los componentes del motor. <button type="button" id="retryEngineCatalog">Reintentar</button><small>${esc(String(error))}</small>`;
      $("#retryEngineCatalog")?.addEventListener("click",()=>loadEngineCatalog());
    }
    throw error;
  }
}
function updateInstallSteps(stage){
  // Downloading/verifying/installing repeat once per downloaded part (an
  // engine can ship as several parts), so the first 3 boxes are treated as a
  // single ongoing phase — otherwise the tracker would flip back to "En
  // espera" on every part instead of only moving forward.
  const normalized=stage==="preparing"?"downloading":stage==="done"?"testing":stage;
  const inPartCycle=normalized==="downloading"||normalized==="verifying"||normalized==="installing";
  const pastPartCycle=normalized==="testing";
  [...el.setupSteps.children].forEach((row,index)=>{
    let completed,active;
    if(index<3){
      completed=stage==="done"||pastPartCycle;
      active=!completed&&inPartCycle;
    }else{
      completed=stage==="done";
      active=!completed&&normalized==="testing";
    }
    row.classList.toggle("complete",completed);
    row.classList.toggle("active",active);
    row.querySelector("b").textContent=completed?"Listo":active?"En curso":"En espera";
  });
}
function handleEngineProgress(progress){
  if(!progress)return;
  const pct=Math.max(0,Math.min(100,Number(progress.percent||0)));
  el.setupProgressBar.style.width=`${pct}%`;
  el.setupProgressPercent.textContent=`${Math.round(pct)}%`;
  el.setupProgressBytes.textContent=progress.total_bytes?`${humanBytes(progress.downloaded_bytes)} / ${humanBytes(progress.total_bytes)}`:"Preparando…";
  el.setupProgressMessage.textContent=progress.message||"Preparando componentes…";
  updateInstallSteps(progress.stage);

  const titles={
    preparing:["PREPARANDO MOTOR","Preparando descarga…"],
    downloading:["DESCARGANDO MOTOR","Descargando componentes…"],
    verifying:["VERIFICACIÓN SEGURA","Comprobando archivos…"],
    installing:["INSTALANDO","Preparando el runtime local…"],
    testing:["COMPROBACIÓN FINAL","Probando el motor…"],
    done:["TODO LISTO","Motor preparado."]
  };
  const t=titles[progress.stage]||titles.downloading;
  el.setupProgressKicker.textContent=t[0];
  el.setupProgressTitle.textContent=t[1];
}
async function initEngineBridge(){
  if(!isDesktop()||state.engine.bridgeReady)return;
  const event=await import("@tauri-apps/api/event");
  tauriListenFn=event.listen;
  engineUnlisten=await tauriListenFn("engine-install-progress",evt=>handleEngineProgress(evt.payload));
  engineCrashUnlisten=await tauriListenFn("engine-crashed",()=>handleEngineCrash());
  state.engine.bridgeReady=true;
}
async function handleEngineCrash(){
  if(state.engine.recovering)return;
  state.engine.recovering=true;
  if(state.generationController)cancelGeneration();
  el.strip.classList.add("visible","error");el.strip.classList.remove("success");
  el.stripTitle.textContent="Motor detenido";
  el.stripText.textContent="El motor local se detuvo inesperadamente. Reiniciando…";
  toast("El motor local se detuvo inesperadamente. Reiniciando…","error");
  try{
    await startTauriEngine();
    if(!(await waitEngine()))throw new Error("El motor no respondió tras reiniciarlo.");
    el.strip.classList.remove("error");el.strip.classList.add("success");
    el.stripTitle.textContent="Motor reiniciado";
    el.stripText.textContent="Ya puedes seguir generando.";
    hideStrip(1800);
    toast("Motor local reiniciado.","success");
    await refreshData();
  }catch{
    el.stripTitle.textContent="No se pudo reiniciar el motor";
    el.stripText.textContent="Cierra y vuelve a abrir Voice Studio AI.";
    toast("No se pudo reiniciar el motor local. Cierra y vuelve a abrir la app.","error");
  }finally{
    state.engine.recovering=false;
  }
}
async function installSelectedEngine(){
  const flavor=state.engine.selectedFlavor;
  const pack=enginePackageFor(flavor);
  if(!pack||state.engine.installing)return;
  state.engine.installing=true;
  openEngineSetup("engineProgressView",false);
  el.cancelEngineInstall.disabled=false;
  handleEngineProgress({stage:"preparing",percent:0,downloaded_bytes:0,total_bytes:pack.download_bytes||0,message:"Preparando una descarga segura…"});
  try{
    const status=await tauriInvoke("install_engine",{flavor});
    state.engine.status=status;
    updateEngineMini();
    handleEngineProgress({stage:"done",percent:100,downloaded_bytes:pack.download_bytes||0,total_bytes:pack.download_bytes||0,message:"Motor instalado y verificado."});
    el.setupDoneMeta.textContent=`${pack.label} ${pack.version} · ${humanBytes(status.installed_bytes)} instalados.`;
    engineViews("engineDoneView");
  }catch(error){
    const message=String(error);
    state.engine.installing=false;
    el.cancelEngineInstall.disabled=true;
    engineViews("engineIntroView");
    el.engineCatalogError.hidden=false;
    el.engineCatalogError.innerHTML=`No se pudo completar la instalación.<small>${esc(message)}</small>`;
    toast(message,"error");
    return;
  }
  state.engine.installing=false;
  el.cancelEngineInstall.disabled=true;
}
async function refreshEngineStatus(){
  if(!isDesktop())return null;
  try{
    const status=await tauriInvoke("engine_status");
    state.engine.status=status;
    updateEngineMini();
    return status;
  }catch(error){
    console.error(error);
    return null;
  }
}
async function showFirstRunEngine(){
  configureEngineIntro("install");
  openEngineSetup("engineIntroView",false);
  try{await loadEngineCatalog()}catch{}
}
async function showEngineUpdate(){
  configureEngineIntro("update");
  openEngineSetup("engineIntroView",false);
  try{
    await loadEngineCatalog();
    const current=state.engine.status?.flavor;
    if(current&&enginePackageFor(current))selectEngineFlavor(current);
  }catch{}
}
async function showEngineManager(){
  const status=await refreshEngineStatus();
  if(status?.installed){
    el.manageEngineTitle.textContent=`${status.label||"Motor local"} · ${status.version||""}`;
    el.manageEngineMeta.textContent=`${humanBytes(status.installed_bytes)} · ${status.running?"Activo":"Listo para iniciar"}`;
    openEngineSetup("engineManageView",true);
    loadEngineCatalog({showErrors:false}).catch(()=>{});
  }else{
    configureEngineIntro("install");
    openEngineSetup("engineIntroView",true);
    loadEngineCatalog().catch(()=>{});
  }
}
async function repairEngine(){
  if(state.engine.installing)return;
  try{
    await loadEngineCatalog();
    const current=state.engine.status?.flavor;
    if(current&&enginePackageFor(current))selectEngineFlavor(current);
    installSelectedEngine();
  }catch{}
}
async function removeEngine(){
  if(state.engine.installing)return;
  if(!confirm("¿Desinstalar el motor local? Tus voces, música, historial y modelos se conservarán."))return;
  try{
    await tauriInvoke("uninstall_engine");
    state.engine.status=await tauriInvoke("engine_status");
    updateEngineMini();
    closeEngineSetup();
    toast("Motor local desinstalado. Tus datos se conservaron.","success");
    setTimeout(()=>showFirstRunEngine(),250);
  }catch(error){toast(String(error),"error")}
}

function initTheme(){
  const t=localStorage.getItem("vsa-theme")||(matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light");document.documentElement.dataset.theme=t;el.theme.innerHTML=t==="dark"?icons.sun:icons.moon
}
async function startTauriEngine(){if(!isDesktop())return;await tauriInvoke("start_engine")}
async function waitEngine(){for(let i=0;i<60;i++){try{await api("/api/health");return true}catch{await new Promise(r=>setTimeout(r,600))}}return false}

el.script.oninput=()=>{el.count.textContent=`${el.script.value.length} / 3000`;estimateDuration();updateGenerate()};
el.voiceSelector.onclick=e=>{
  e.preventDefault();
  e.stopPropagation();
  openSheet("voice");
};
el.modelSelector.onclick=e=>{
  e.preventDefault();
  e.stopPropagation();
  openSheet("model");
};
el.selectorBack.onclick=e=>{
  e.preventDefault();
  e.stopPropagation();
  closeSheet(state.activeSheet,{focus:true});
};
el.voiceList.onclick=e=>{
  const previewButton=e.target.closest("[data-preview-voice]");
  if(previewButton){
    e.preventDefault();
    e.stopPropagation();
    preview(`${API}/api/voices/${encodeURIComponent(previewButton.dataset.previewVoice)}/audio`,previewButton);
    return;
  }

  const selectButton=e.target.closest("[data-select-voice]");
  if(!selectButton) return;

  const voice=state.voices.find(v=>v.id===selectButton.dataset.selectVoice)||null;
  if(!voice) return;

  state.voice=voice;
  updateVoiceUI();
  renderVoices(el.voiceSearch.value);
  closeSheet("voice",{focus:true});
};

function handleModelListClick(e){
  const installButton=e.target.closest("[data-install-model]");
  if(installButton){
    e.preventDefault();
    e.stopPropagation();
    installModel(installButton.dataset.installModel);
    return;
  }

  const button=e.target.closest("[data-model]");
  if(!button) return;

  e.preventDefault();
  e.stopPropagation();

  if(button.dataset.disabled==="true"){
    toast("Este motor necesita un adaptador específico antes de poder ejecutarlo.","error");
    return;
  }

  if(selectModel(button.dataset.model)){
    closeSheet("model",{focus:true});
  }
}
el.compatibleModelList.onclick=handleModelListClick;
el.modelSearchResults.onclick=handleModelListClick;
el.installSelectedModel.onclick=()=>{
  const model=selectedModel();
  if(model)installModel(model.id);
};
el.voiceSearch.oninput=()=>renderVoices(el.voiceSearch.value);el.modelSearch.oninput=searchModels;
el.addVoice.onclick=()=>el.voiceFile.click();el.voiceFile.onchange=()=>{const f=el.voiceFile.files?.[0];if(f)prepareImport(f);el.voiceFile.value=""};
el.voiceImportForm.onsubmit=async e=>{if(e.submitter?.value==="cancel")return;e.preventDefault();if(!state.pendingVoiceFile)return;el.confirmVoiceImport.disabled=true;try{await importVoice(state.pendingVoiceFile,el.importTranscript.value.trim());el.voiceImportDialog.close();state.pendingVoiceFile=null;toast("Voz importada y preparada.","success")}catch(err){toast(err.message,"error")}finally{el.confirmVoiceImport.disabled=false}};
el.improveClone.onclick=openTranscript;el.transcriptForm.onsubmit=async e=>{if(e.submitter?.value==="cancel")return;e.preventDefault();try{await saveTranscript(el.transcriptInput.value.trim());el.transcriptDialog.close();toast("Transcripción guardada.","success")}catch(err){toast(err.message,"error")}};
el.removeTranscript.onclick=async()=>{try{await saveTranscript("");el.transcriptDialog.close();toast("Transcripción eliminada.")}catch(e){toast(e.message,"error")}};
el.addSound.onclick=()=>el.soundFile.click();
el.repairSounds.onclick=async()=>{
  el.repairSounds.disabled=true;
  el.repairSounds.textContent="Revisando biblioteca…";
  try{
    const result=await api("/api/sounds/repair",{method:"POST"});
    await refreshData();
    const repaired=result.repaired?.length||0;
    const bad=result.quarantined?.length||0;
    if(bad){
      toast(`${repaired} reparada(s). ${bad} archivo(s) inválidos fueron apartados.`,"error");
    }else{
      toast(`${repaired} música(s) convertidas. Biblioteca lista.`,"success");
    }
  }catch(e){
    toast(e.message,"error");
  }finally{
    el.repairSounds.disabled=false;
    el.repairSounds.textContent="Reparar biblioteca de música";
  }
};
el.soundFile.onchange=async()=>{const f=el.soundFile.files?.[0];if(!f)return;try{
  const data=await importSound(f);
  toast(`Música preparada: ${data.name} · ${Number(data.duration||0).toFixed(1)} s · WAV interno`,"success");
}catch(e){
  toast(e.message,"error");
}finally{el.soundFile.value=""}};
el.previewSound.onclick=()=>{
  const id=state.selectedSoundId;
  if(id)preview(`${API}/api/sounds/${encodeURIComponent(id)}/audio`,el.previewSound);
};
$$(".tabs button").forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));el.historySearch.oninput=renderHistory;el.clearHistory.onclick=async()=>{await api("/api/history",{method:"DELETE"});state.history=[];renderHistory();toast("Historial borrado.")};
el.generate.onclick=generate;el.cancelGeneration.onclick=cancelGeneration;$$("#profileButtons button").forEach(b=>b.onclick=()=>applyProfile(b.dataset.profile));
[el.speed,el.pitch].forEach(x=>x.oninput=()=>{syncLabels();state.profile="custom";$$("#profileButtons button").forEach(b=>b.classList.remove("active"));savePreferences()});
[el.stability,el.style].forEach(x=>x.oninput=()=>{state.profile="custom";$$("#profileButtons button").forEach(b=>b.classList.remove("active"));savePreferences()});
[el.output,el.mode].forEach(x=>x.onchange=savePreferences);
el.soundSelect.onchange=()=>{
  stopPreview();
  state.selectedSoundId=el.soundSelect.value||"";
  updateMusicUI();
  savePreferences();
};
el.musicVolume.oninput=()=>{
  syncLabels();
  updateMusicUI();
  savePreferences();
};
el.applyMusic.onclick=()=>updateResultMusic(state.selectedSoundId||null);
el.removeMusic.onclick=()=>updateResultMusic(null);
el.speakerBoost.onclick=()=>{toggle(el.speakerBoost);savePreferences()};el.reset.onclick=()=>{state.profile="natural";applyProfile("natural",false);el.mode.value="auto";el.output.value="wav";savePreferences();toast("Valores restablecidos.")};

el.installEngineButton.onclick=installSelectedEngine;
el.cancelEngineInstall.onclick=async()=>{
  el.cancelEngineInstall.disabled=true;
  el.setupProgressMessage.textContent="Cancelando de forma segura…";
  try{await tauriInvoke("cancel_engine_install")}catch{}
};
el.enterStudioButton.onclick=async()=>{
  closeEngineSetup();
  await launchWorkspace();
};
el.manageEngine.onclick=showEngineManager;
el.engineSetupClose.onclick=closeEngineSetup;
el.repairEngineButton.onclick=repairEngine;
el.uninstallEngineButton.onclick=removeEngine;

$$(".quick-prompts button").forEach(b=>b.onclick=()=>{el.script.value=b.dataset.prompt;el.script.dispatchEvent(new Event("input"))});
$$(".help").forEach(b=>{b.onmouseenter=()=>{el.tooltip.textContent=b.dataset.tip;const r=b.getBoundingClientRect();el.tooltip.style.left=`${Math.min(innerWidth-300,Math.max(10,r.left-240))}px`;el.tooltip.style.top=`${r.bottom+7}px`;el.tooltip.classList.add("show")};b.onmouseleave=()=>el.tooltip.classList.remove("show")});
el.theme.onclick=()=>{const t=document.documentElement.dataset.theme==="dark"?"light":"dark";document.documentElement.dataset.theme=t;localStorage.setItem("vsa-theme",t);el.theme.innerHTML=t==="dark"?icons.sun:icons.moon;drawWaveform()};
window.addEventListener("keydown",e=>{
  if(e.key==="Escape" && state.activeSheet && !document.querySelector("dialog[open]")){
    e.preventDefault();
    closeSheet(state.activeSheet,{focus:true});
    return;
  }
  if((e.ctrlKey||e.metaKey)&&e.key==="Enter"&&!el.generate.disabled){
    e.preventDefault();
    generate();
  }
});
document.addEventListener("pointerdown",e=>{const b=e.target.closest(".pressable");if(b)b.classList.add("is-pressed")},{passive:true});
document.addEventListener("pointerup",()=>$$(".is-pressed").forEach(x=>x.classList.remove("is-pressed")),{passive:true});
document.addEventListener("pointercancel",()=>$$(".is-pressed").forEach(x=>x.classList.remove("is-pressed")),{passive:true});
document.addEventListener("click",e=>{
  if(!e.target.closest(".volume-wrap"))el.volumePopover.classList.remove("open");
  if(!e.target.closest(".music-wrap"))el.musicPopover.classList.remove("open");
});

async function launchWorkspace(){
  if(state.engine.bootStarted)return;
  state.engine.bootStarted=true;
  try{
    await startTauriEngine();
    if(!(await waitEngine()))throw new Error("El motor local no pudo iniciarse.");
    await refreshEngineStatus();
    await refreshData();
    syncLabels();
  }catch(error){
    state.engine.bootStarted=false;
    const message=String(error);
    if(message.includes("ENGINE_NOT_INSTALLED")){
      await showFirstRunEngine();
      return;
    }
    toast(message,"error");
  }
}
async function boot(){
  initTheme();
  wirePlayer();
  closeAllSheets();
  switchTab("settings");

  if(!isDesktop()){
    await launchWorkspace();
    return;
  }

  await initEngineBridge();
  const status=await refreshEngineStatus();
  if(!status?.installed){
    await showFirstRunEngine();
    return;
  }
  if(versionIsOlder(status.version,REQUIRED_ENGINE_VERSION)){
    await showEngineUpdate();
    return;
  }
  await launchWorkspace();
}
boot();
