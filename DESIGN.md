# Design Read — Qwen Voice Studio v0.5

Page kind: desktop creative utility / local AI audio tool.

Audience:
- Spanish-speaking users creating short advertising spots and voiceovers.
- Users should not need to understand Qwen internals.

Primary task:
1. Write script.
2. Choose voice.
3. Check reference health.
4. Choose Fiel / Natural / Spot.
5. Generate.
6. Listen / download.

Design direction:
- restrained;
- technical;
- editorial;
- compact;
- desktop-first;
- one green accent.

Taste Skill dials:
- DESIGN_VARIANCE: 4/10
- MOTION_INTENSITY: 4/10
- VISUAL_DENSITY: 7/10

Large-screen rule:
- editor text is capped at ~1080–1160 px readable canvas;
- settings rail uses clamp(420px, 24vw, 500px);
- whitespace belongs around the editor, not inside stretched text lines.

Motion:
- panel reveal for voices;
- sliding tabs;
- modal reveal;
- staggered voice/history list;
- beam only while generating;
- temporary processing strip;
- reduced motion supported.

Anti-slop rules:
- no permanent decorative AI orb;
- no fake Similarity control;
- no giant hero UI;
- no gradient-card wall;
- no unnecessary pills;
- no hidden expert terms in the primary flow.
