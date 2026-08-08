import "./styles.css";

const API = "http://127.0.0.1:8765";
const DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base";

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
  external: `<svg viewBox="0 0 24 24"><path d="M14 5h5v5M19 5l-8 8"/><path d="M18 13v6H5V6h6"/></svg>`
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
  activeSheet: null,
  selectedSoundId: ""
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

            <div class="setting-block">
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

            <div class="setting-block compact-top">
              <label>Música de fondo</label>
              <div class="sound-picker-row">
                <div class="select-native">
                  <select id="soundSelect"><option value="">Sin música</option></select>
                  ${icons.chevron}
                </div>
                <button class="icon-button pressable" id="previewSound" title="Escuchar">${icons.play}</button>
                <button class="icon-button pressable" id="addSound" title="Agregar música">${icons.plus}</button>
              </div>
              <button class="repair-library pressable" id="repairSounds" type="button">Reparar biblioteca de música</button>
              <div class="slider-setting music-volume-setting">
                <div class="slider-title"><label>Volumen</label><output id="musicVolumeValue">18%</output></div>
                <input id="musicVolume" type="range" min="5" max="40" value="18" step="1">
              </div>
              <p class="music-status" id="musicStatus">Sin música. El archivo final contendrá solo la locución.</p>
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
  strip: $("#generationStrip"), stripTitle: $("#generationTitle"), stripText: $("#generationText"), stripEngine: $("#generationEngine"), orb: $("#thinkingOrb"),
  generate: $("#generateButton"), generateIcon: $("#generateIcon"), generateText: $("#generateText"), transport: $("#transport"),
  audio: $("#resultAudio"), player: $("#audioPlayer"), playerPlay: $("#playerPlay"), playerCurrent: $("#playerCurrent"),
  playerDuration: $("#playerDuration"), waveform: $("#waveform"), volumeButton: $("#volumeButton"), volumePopover: $("#volumePopover"),
  playerVolume: $("#playerVolume"), download: $("#downloadButton"), bottomVoice: $("#bottomVoice"), bottomMode: $("#bottomMode"),
  hardware: $("#hardwareText"), voiceSelector: $("#voiceSelector"), selectedVoiceName: $("#selectedVoiceName"), selectedVoiceMeta: $("#selectedVoiceMeta"),
  referenceScore: $("#referenceScore"), referenceLabel: $("#referenceLabel"), referenceDetails: $("#referenceDetails"), improveClone: $("#improveClone"),
  modelSelector: $("#modelSelector"), selectedModelAvatar: $("#selectedModelAvatar"), selectedModelName: $("#selectedModelName"), selectedModelMeta: $("#selectedModelMeta"),
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
  tooltip: $("#tooltip"), toast: $("#toast")
};

function esc(v){return String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;")}
function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
function fmtTime(v){if(!Number.isFinite(v)||v<0)return"0:00";const m=Math.floor(v/60),s=Math.floor(v%60);return`${m}:${String(s).padStart(2,"0")}`}
function prettyDate(v){try{return new Intl.DateTimeFormat("es-PE",{dateStyle:"medium",timeStyle:"short"}).format(new Date(v))}catch{return""}}

async function api(path, options={}){
  const r=await fetch(`${API}${path}`,{cache:"no-store",...options});
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
  if(!m)return;
  el.selectedModelName.textContent=m.name;
  el.selectedModelMeta.textContent=`${m.recommended?"Recomendado · ":""}Compatible · ${m.disk_gb?`${m.disk_gb} GB`:"local"}`;
  el.selectedModelAvatar.innerHTML=`${m.avatar_url?`<img src="${esc(m.avatar_url)}" alt="">`:""}<span>${authorMark(m)}</span>`;
  installAvatarFallbacks(el.selectedModelAvatar);
  el.bottomMode.textContent=m.name;
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
  const meta=[
    m.family,
    m.disk_gb?`${m.disk_gb} GB`:null,
    m.license,
  ].filter(Boolean).join(" · ");
  return `<div class="model-row ${state.model?.id===m.id?"selected":""}" style="--i:${i}">
    ${avatarHTML(m)}
    <button class="model-main" data-model="${esc(m.id)}" ${selectable&&m.compatible?"":"data-disabled='true'"}>
      <span class="model-title-line"><strong>${esc(m.name)}</strong>${m.recommended?`<em>Recomendado</em>`:""}</span>
      <small>${esc(meta||m.author||"Hugging Face")}</small>
      ${m.compatibility_note?`<p>${esc(m.compatibility_note)}</p>`:""}
    </button>
    <span class="compat-badge ${m.compatible?"ok":"adapter"}">${m.compatible?"Compatible":"Adaptador"}</span>
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

  if(selected){
    el.musicStatus.innerHTML=`<strong>${esc(selected.name)}</strong> · ${el.musicVolume.value}% · se mezclará y guardará dentro del archivo final.`;
  }else{
    el.musicStatus.textContent="Sin música. El archivo final contendrá solo la locución.";
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
function updateGenerate(){el.generate.disabled=!(state.voice&&selectedModel()?.compatible&&el.script.value.trim())||state.busy}
function savePreferences(){
  try{
    localStorage.setItem("vsa-settings",JSON.stringify({
      model_id:selectedModel()?.id||DEFAULT_MODEL_ID,profile:state.profile,speed:el.speed.value,stability:el.stability.value,style:el.style.value,
      pitch:el.pitch.value,output:el.output.value,mode:el.mode.value,musicVolume:el.musicVolume.value,soundId:state.selectedSoundId,boost:el.speakerBoost.classList.contains("on")
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
    el.output.value=p.output||"wav";el.mode.value=p.mode||"auto";el.musicVolume.value=p.musicVolume||18;state.selectedSoundId=p.soundId||"";
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
    pitch_semitones:Number(el.pitch.value),speaker_boost:el.speakerBoost.classList.contains("on"),output_format:el.output.value,
    music_id:state.selectedSoundId||null,music_volume:Number(el.musicVolume.value)/100
  }
}

function setBusy(on){
  state.busy=on;updateGenerate();el.generate.classList.toggle("generating",on);el.orb.classList.toggle("thinking",on);
  if(on){
    el.strip.classList.add("visible");el.strip.classList.remove("success","error");el.generateIcon.innerHTML=`<span class="spinner"></span>`;el.generateText.textContent="Generando";
  }else{
    el.generateIcon.innerHTML=icons.spark;el.generateText.textContent=state.result?"Regenerar":"Generar";
  }
}
function hideStrip(delay=1300){clearTimeout(hideStrip.t);hideStrip.t=setTimeout(()=>el.strip.classList.remove("visible","success","error"),delay)}
function stageFor(st){
  const map={
    checking:["Comprobando hardware","Seleccionando el mejor modo para este modelo."],
    loading_model:["Cargando modelo","La primera carga puede descargar varios GB y quedará en caché."],
    preparing_voice:["Preparando referencia","Leyendo identidad vocal y contexto ICL."],
    generating:["Generando locución","Sintetizando la voz localmente."],
    postprocessing:["Ajustando audio","Aplicando velocidad, tono y realce local."],
    mixing:["Mezclando música","Aplicando el fondo seleccionado al archivo final."],
    saving:["Guardando resultado","Escribiendo el archivo final."],
    done:["Locución lista","El reproductor ya está disponible."]
  };
  const [a,b]=map[st.stage]||["Procesando",st.message||"Trabajando localmente."];el.stripTitle.textContent=a;el.stripText.textContent=b;el.stripEngine.textContent=String(st.backend||"LOCAL").toUpperCase()
}
function pollStatus(){clearInterval(state.statusTimer);state.statusTimer=setInterval(async()=>{try{stageFor(await api("/api/status"))}catch{}},650)}

async function generate(){
  if(!state.voice||!selectedModel()?.compatible||!el.script.value.trim())return;
  stopPreview();setBusy(true);pollStatus();
  try{
    const result=await api("/api/generate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(settingsPayload())});
    const url=`${API}${result.url}`,name=result.filename;
    state.result=result;
    await setResultAudio(url,name,state.voice.name);
    el.strip.classList.add("success");
    el.stripTitle.textContent="Locución lista";
    el.stripText.textContent=`${result.model_name} · ${result.backend.toUpperCase()} · ${result.used_transcript?"ICL":"X-vector"}${result.music_name?` · ♪ ${result.music_name}`:""}`;
    await refreshData();toast("Locución generada.","success");hideStrip(1450);
  }catch(e){
    el.strip.classList.add("visible","error");el.stripTitle.textContent="No se pudo generar";el.stripText.textContent=e.message;toast(e.message,"error");hideStrip(4300);
  }finally{clearInterval(state.statusTimer);state.statusTimer=null;setBusy(false)}
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

function initTheme(){
  const t=localStorage.getItem("vsa-theme")||(matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light");document.documentElement.dataset.theme=t;el.theme.innerHTML=t==="dark"?icons.sun:icons.moon
}
async function startTauriEngine(){if(!window.__TAURI_INTERNALS__)return;try{const{invoke}=await import("@tauri-apps/api/core");await invoke("start_engine")}catch(e){console.error(e)}}
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
el.generate.onclick=generate;$$("#profileButtons button").forEach(b=>b.onclick=()=>applyProfile(b.dataset.profile));
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
el.speakerBoost.onclick=()=>{toggle(el.speakerBoost);savePreferences()};el.reset.onclick=()=>{state.profile="natural";applyProfile("natural",false);el.mode.value="auto";el.output.value="wav";savePreferences();toast("Valores restablecidos.")};
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
document.addEventListener("click",e=>{if(!e.target.closest(".volume-wrap"))el.volumePopover.classList.remove("open")});

async function boot(){
  initTheme();
  wirePlayer();
  closeAllSheets();
  switchTab("settings");
  await startTauriEngine();
  if(!(await waitEngine()))return toast("El motor local no pudo iniciarse.","error");
  try{await refreshData();syncLabels()}catch(e){toast(e.message,"error")}
}
boot();
