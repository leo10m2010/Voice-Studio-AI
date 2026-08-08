# Qwen Voice Studio v0.5 — Research decisions

## 1. Reference length

Qwen officially describes both Base checkpoints as capable of rapid voice cloning from about 3 seconds of reference audio.

That should be treated as a minimum capability, not a universal optimum.

Practical reports vary:
- one user benchmark reported excellent Qwen3-TTS speaker similarity from a 7-second clip;
- community Qwen workflows commonly accept roughly 5–30 seconds;
- some users report better consistency around 20–30 seconds, particularly with the 1.7B Base model;
- reference quality matters more than simply making the clip longer.

For this app the practical guidance is therefore:
- minimum warning: < 3 s;
- acceptable: 3–8 s;
- recommended test range: 8–25 s;
- usable but review: 25–35 s;
- long reference warning: > 35 s.

The app does not automatically cut a long reference because the most useful segment depends on the style the user wants to preserve.

## 2. Reference quality matters more than a fake Similarity slider

Qwen Base does not expose an ElevenLabs-style `similarity_boost`.

The strongest native fidelity mechanism exposed by Qwen is:
- reference audio;
- exact reference transcript;
- `x_vector_only_mode=False`, which enables ICL.

When the transcript is missing:
- `x_vector_only_mode=True`;
- only the speaker embedding is used;
- official Qwen documentation warns that clone quality can be lower.

Because of that, v0.5 removes the fake Similarity slider and replaces it with a reference-quality meter.

The meter evaluates:
- duration;
- RMS level;
- clipping;
- exact transcript availability.

It is a reference-health score, not an embedding similarity score.

## 3. Reference preprocessing

Every voice is now prepared conservatively as:
- mono;
- 24 kHz;
- leading/trailing silence trimmed;
- DC offset removed;
- RMS normalized toward -20 dBFS;
- peak protected below clipping.

No denoising or aggressive EQ is applied automatically because those processes can alter timbre.

The original file remains untouched.

## 4. Exact transcript and language

The application is optimized for Spanish.

For a Spanish clone:
- use a Spanish reference where possible;
- write the transcript exactly as spoken;
- preserve the speaker style you want to reproduce.

Community Qwen tooling also recommends using the speaker's native language for the most stable results.

## 5. Reusable clone prompt

Qwen officially supports:
`create_voice_clone_prompt(...)`

and recommends reusing the result for repeated generations with the same speaker.

v0.5 now caches this prompt in memory per:
- reference file;
- transcript;
- processing backend.

This avoids re-extracting the reference features every generation.

## 6. Stability presets

ElevenLabs documents a common starting point around:
- stability ~0.50;
- similarity ~0.75;
- style 0;
- speed 1.0.

It also notes that high style exaggeration can reduce stability.

Those numbers cannot be copied directly to Qwen because Qwen's controls differ.

v0.5 therefore uses:

### Fiel
- deterministic generation (`do_sample=False`);
- stability UI 82;
- style 0;
- speed 1.00;
- pitch 0;
- speaker boost off.

Purpose: repeatability and speaker consistency.

### Natural
- sampled generation;
- stability UI 55;
- style 0;
- speed 1.00;
- pitch 0;
- speaker boost on.

Purpose: neutral starting point.

### Spot
- sampled generation;
- stability UI 45;
- style 20;
- speed 1.04;
- pitch 0;
- speaker boost on.

Purpose: slightly livelier advertising delivery without pushing style to extremes.

## 7. Long text

Real Qwen3-TTS reports include speaking-rate drift on long generations.

Community implementations frequently split long text at sentence boundaries.

v0.5 automatically chunks long scripts around punctuation and joins the resulting audio with a short silence.

Short spots are not split.

## 8. max_new_tokens

A community Qwen implementation notes that overly large `max_new_tokens` values can produce excessive trailing audio or humming.

v0.5 calculates a dynamic token budget from text length instead of always using 4096.

## 9. 0.6B versus 1.7B

The 0.6B model remains the default because it is the realistic choice for the current hardware.

Community reports often prefer 1.7B for clone quality, but PyTorch implementations can require substantially more VRAM. One Windows-oriented project recommends roughly:
- 0.6B: around 8 GB+ VRAM;
- 1.7B: around 16 GB+ VRAM.

That makes 1.7B a poor automatic choice for a 2 GB GPU and uncertain on an 8 GB RTX 4060.

Recent llama.cpp / C++ work around Qwen3-TTS is promising for a future desktop backend because it can use CPU/GPU hybrid inference, but it is too new to replace the current working PyTorch path without quality testing.

## 10. UI / UX research

The app is a desktop creative utility, not a dashboard or marketing page.

Taste Skill principles applied:
- one accent color;
- consistent radius system;
- restrained hierarchy;
- task-first composition;
- no generic card wall;
- no decorative gradients as primary structure;
- higher information density in the settings panel;
- editor content capped on large screens instead of stretching across the whole display.

Transitions.dev principles applied:
- panel reveal;
- tab indicator;
- modal scale/reveal;
- list staggering;
- spinner to success;
- toast reveal;
- reduced-motion support;
- motion never carries critical information by itself.

Large-screen behavior:
- editor canvas has a maximum readable width;
- settings rail grows only up to a controlled maximum;
- the main editor retains intentional whitespace instead of stretching each line across ultrawide screens.

## Sources reviewed

Official:
- https://github.com/QwenLM/Qwen3-TTS
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py
- https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech
- https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning
- https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices
- https://www.tasteskill.dev/docs
- https://transitions.dev/

Community implementations / reports reviewed:
- 1038lab/ComfyUI-QwenTTS
- SUP3RMASS1VE/Qwen3-TTS
- PGCRT/ComfyUI-QWEN3_TTS
- Qwen3-TTS cloning tests and user reports on Reddit
- Qwen official issues concerning long-text rate drift and ICL reference-tail echo


---

# v0.6 — Multi-model architecture, Hugging Face discovery and custom player

## Model selection

The application now separates:
1. **Compatible models**: models that can actually run through the installed engine adapter.
2. **Hugging Face discovery**: public TTS models returned by Hub search.

This distinction matters because Hugging Face repositories do not share one universal runtime API.
Qwen3-TTS, Chatterbox, OpenVoice and XTTS each require different loaders and generation calls.

Directly compatible in v0.6:
- Qwen/Qwen3-TTS-12Hz-0.6B-Base — recommended.
- Qwen/Qwen3-TTS-12Hz-1.7B-Base — heavier quality option.

Curated discovery:
- ResembleAI/Chatterbox-Multilingual-es-mx-latam.
- myshell-ai/OpenVoiceV2.

Hub search uses `huggingface_hub.HfApi.list_models()` with the text-to-speech filter.
Author avatars are retrieved best-effort from the public user/organization overview endpoints.

## Player

The browser-native audio control was removed.

The new player includes:
- play / pause;
- decoded waveform;
- direct pointer seeking;
- elapsed and total time;
- volume popover;
- download;
- Generate → processing → player materialization transition.

The waveform is created from the generated audio using Web Audio API and does not require an external dependency.

## Apple-design pass

Applied principles:
- pointer-down press feedback;
- same-path sheet enter/exit;
- source-anchored popover for volume;
- floating bottom chrome uses restrained translucency;
- no persistent decorative orb;
- interruptible pointer seeking;
- system font;
- `prefers-reduced-motion`;
- `prefers-reduced-transparency`;
- `prefers-contrast: more`.

## Windows export

`npm run build:windows`

builds:
1. frontend;
2. PyInstaller engine folder;
3. Tauri app;
4. NSIS setup executable.

The model weights are intentionally not bundled in the installer; they are downloaded on first use and cached.
