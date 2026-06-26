# Handoff: PDF Translator — Single-Page Redesign

## Overview
A single-page web app that lets a user upload a PDF, pick source/target languages, run a
translation, and read the **original** and **translated** text side by side. This is the only
page in the app. The design is a refined, "translator-app" style: light neutral canvas, a single
blue accent, squared (non-rounded) container edges, and a two-pane reader.

## About the Design Files
The file in this bundle (`PDF Translator.dc.html`) is a **design reference created in HTML** — a
prototype showing intended look and behavior, **not production code to copy directly**. It is
authored in a streaming "Design Component" format (custom `<x-dc>`, `<sc-if>` tags and an inline
logic class) that is specific to the prototyping tool; **do not** port that scaffolding.

Your task is to **recreate this design in the target codebase's existing environment** (React,
Vue, Svelte, etc.) using its established patterns, component library, and styling approach. If no
frontend exists yet, choose the most appropriate framework for the project and implement it there.
Read the HTML purely as a visual + behavioral spec — every value you need is documented below.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, and layout are specified. Recreate the
UI to match these values. The only intentionally "mock" parts are the **content** (a sample climate
report and its Chinese translation) and the **states** (it always shows an uploaded file + a
completed translation) — those are placeholders to demonstrate the populated view; wire them to real
data and real app states.

## Layout (top to bottom, single centered column)
- Page background `#F8F9FA`. Content is centered in a column with `max-width: 1180px`,
  horizontal padding `40px`, top padding `30px`, bottom padding `64px`.
- Vertical order:
  1. **Header row** — wordmark (left) + History button (right). `margin-bottom: 26px`.
  2. **Dropzone** — full-width dashed upload box.
  3. **Controls row** — From select · swap button · To select · Translate button. `margin-top: 22px`.
  4. **Status bar** — translation-complete banner + download button. `margin-top: 20px`.
  5. **Panes** — ORIGINAL and TRANSLATED, side by side, `gap: 22px`, `margin-top: 30px`.
- All container corners are **square** (`border-radius: 0`) except circular elements (status check
  dot, "Ready" dot). Standard border is `1px solid #DADCE0`.
- Entrance: each major block fades + rises in on load (`translateY(12px)` → `0`, opacity `0` → `1`,
  `0.5s cubic-bezier(.2,.8,.2,1)`), staggered by delays `0 / .04 / .1 / .16 / .22s`. Optional polish.

## Components

### 1. Header
- **Wordmark** (left): a `30×30px` solid accent square (`background: var(--accent)`) containing the
  glyph "文" (white, `15px`, weight 700), followed by gap `11px`, then the text "PDF Translator"
  (`21px`, weight 700, color `#202124`, letter-spacing `-0.015em`).
- **History button** (right): pill-less rectangular button, `height 38px`, padding `0 15px`,
  `1px solid #DADCE0`, white bg, font `13.5px`/weight 500, color `#5F6368`. Leading clock-with-arrow
  icon (`16px`, stroke 1.6). Hover: background `#F1F3F4`. Opens translation history (functional).

### 2. Dropzone
- Box: `border: 2px dashed #C4C7CC`, white bg, padding `56px 32px`, centered text.
- Hover/drag-over: border → accent, background → `color-mix(in srgb, var(--accent) 4%, #fff)`.
- Contents (centered, stacked):
  - Upload icon in a `52×52px` accent-tint square (`color-mix(... 9%, #fff)`), accent stroke, `margin-bottom 18px`.
  - Line: "Drag & drop a PDF here, or **browse**" — `18px`, color `#3C4043`; "browse" is accent,
    weight 600, underlined, clickable (triggers file picker).
  - Sub-line (shown when a file is loaded): file icon + filename + "·" + "1.2 MB · 8 pages",
    `13.5px`, color `#5F6368`. The "·" separators are color `#C4C7CC`.

### 3. Controls row (`display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap`)
- **From / To selects**: each is a labeled control. Label above (`13px`, weight 500, `#5F6368`),
  gap `7px`. Select: `height 46px`, `min-width 200px`, padding `0 40px 0 15px`, `1px solid #DADCE0`,
  white bg, `14.5px`/weight 500, color `#202124`. Native chevron removed (`appearance:none`); a
  custom chevron-down icon is absolutely positioned `right:14px`, vertically centered, `#5F6368`,
  `pointer-events:none`.
  - **From options:** Auto-detect, English, Chinese (Simplified), Portuguese.
  - **To options:** Chinese (Simplified), English, Portuguese.
- **Swap button**: `46×46px` square, `1px solid #DADCE0`, white, icon `#5F6368`. Hover: border +
  icon → accent. The icon rotates `180deg` over `0.45s cubic-bezier(.2,.8,.2,1)` on hover. Swaps the
  From/To language selections.
- **Translate button** (primary): `height 46px`, padding `0 24px`, no border, `background: var(--accent)`,
  white text `14.5px`/weight 600, trailing arrow icon, `margin-left:4px`, shadow
  `0 1px 2px rgba(60,64,67,.18)`. Hover: elevation
  `0 1px 3px rgba(60,64,67,.3), 0 4px 8px 3px rgba(60,64,67,.15)`. Triggers translation.

### 4. Status bar (success state)
- Box: padding `13px 16px`, bg `color-mix(in srgb, #1E8E3E 7%, #fff)`,
  border `1px solid color-mix(in srgb, #1E8E3E 26%, #DADCE0)`, space-between, `flex-wrap`.
- Left: `22px` circular green (`#1E8E3E`) checkmark badge + "Translation complete" (`14px`/600, `#1A7332`)
  + mono meta "8 / 8 pages · 1.4s" (`11.5px`, `#5F7A66`).
- Right: **Download translated PDF** button — `height 36px`, padding `0 15px`, white bg, border
  `1px solid color-mix(in srgb, var(--accent) 30%, #DADCE0)`, accent text `13px`/600, leading
  download icon. Downloads the translated output.
- This bar represents the **completed** state. Other states to design analogously: idle/empty
  (no bar, or "Ready to translate"), in-progress (spinner + "Translating page X of N…", progress),
  error (red variant — the original app showed a raw "500 Server Error"; replace with a friendly
  message + Retry).

### 5. Panes (ORIGINAL / TRANSLATED)
- Two equal flex columns (`flex:1` each), `gap:22px`. Each has a small label row above the card.
- **Label row**: bold uppercase label (`12px`, weight 700, letter-spacing `0.12em`) + a mono
  language badge (`10.5px`, padding `2px 7px`).
  - ORIGINAL: label `#5F6368`, badge "EN" on `#F1F3F4` bg, `#5F6368` text.
  - TRANSLATED: label accent-colored, badge "ZH" on `color-mix(... 12%, #fff)`, accent text.
- **Card**: white bg, `1px solid #DADCE0`. The TRANSLATED card uses an accent-tinted border
  (`color-mix(... 30%, #DADCE0)`) and a soft accent glow shadow
  `0 1px 2px rgba(60,64,67,.08), 0 2px 8px 2px color-mix(in srgb, var(--accent) 8%, transparent)`.
- **Scroll body**: `height 540px`, `overflow-y:auto`, padding `26px 28px`. Custom scrollbar:
  `10px` wide, thumb `#DADCE0` with a `3px solid #fff` inset border, radius `999px`.
  - Body type — Original: H2 `22px`/700, section labels mono `11px` uppercase accent, paragraphs
    `14.5px`/line-height 1.78/`#3C4043`. Translated: uses Noto Sans SC, H2 `23px`/700, paragraphs
    `15px`/line-height 1.95/`#34342F`.
  - **Page markers** (toggleable): a centered mono divider ("PAGE 2" / "第 2 页") between content
    blocks — two `1px #E8EAED` rules flanking `10px` mono `#B0B3B8` text. Render one per page boundary.

## Interactions & Behavior
- **Upload**: click "browse" or drag-drop a PDF onto the dropzone → file is parsed; filename, size,
  and page count populate the sub-line; status moves to idle/ready.
- **Language select / swap**: changing From/To updates the badges (EN/ZH) on the panes. Swap
  exchanges the two and (if already translated) should re-translate or invalidate the result.
- **Translate**: extracts text per page, sends to translation backend, fills the TRANSLATED pane.
  Show in-progress state with per-page progress; on completion show the green status bar + enable
  download.
- **Download**: generates/serves the translated PDF.
- **History**: opens a list of past translations.
- **Scroll**: panes scroll independently in the prototype. Consider **synced scrolling** between
  panes as an enhancement (align by page).
- **Hover/transition specifics** are listed per component above.

## State Management
- `file`: { name, sizeBytes, pageCount, blob/handle } | null
- `sourceLang`: 'auto' | 'en' | 'zh-Hans' | 'pt'
- `targetLang`: 'zh-Hans' | 'en' | 'pt'
- `status`: 'idle' | 'translating' | 'done' | 'error'
- `progress`: { current, total } (during 'translating')
- `originalPages`: string[] (extracted text per page)
- `translatedPages`: string[] (result per page)
- `errorMessage`: string | null
- `showPageMarkers`: boolean (UI preference)
- Transitions: upload → idle; Translate → translating → done | error; swap resets/recomputes result.
- Data: PDF text extraction (e.g. pdf.js) + a translation API. The original app called Google
  Translate and surfaced raw server errors — wrap failures in friendly, retryable messaging.

## Design Tokens
Colors:
- Accent (primary): `#1B66C9` (alternates offered in prototype: `#1E8E3E`, `#C2410C`, `#6D28D9`)
- Page bg: `#F8F9FA`
- Surface / card: `#FFFFFF`
- Border: `#DADCE0`; subtle inner border: `#E8EAED`; faint divider dots: `#C4C7CC`
- Text primary: `#202124`; body: `#3C4043`; secondary/muted: `#5F6368`; faint: `#B0B3B8`
- Success: `#1E8E3E` (text on tint `#1A7332`); success tint bg `color-mix(in srgb,#1E8E3E 7%,#fff)`
- Accent tints via `color-mix(in srgb, var(--accent) N%, #fff)` — 4% (hover), 9% (icon chip), 12% (badge), 30% (translated border)

Typography:
- UI / body: **Hanken Grotesk** (400/500/600/700/800)
- Monospace labels & meta: **IBM Plex Mono** (400/500)
- Chinese (translated pane): **Noto Sans SC** (400/500/700), stack `'Noto Sans SC','Hanken Grotesk',sans-serif`
- Sizes used: 21 (wordmark), 22–23 (H2), 18 (dropzone lead), 14.5–15 (body/controls), 13.5/13 (buttons/meta),
  12 (pane labels), 11/11.5/10.5/10 (mono labels/badges). Letter-spacing: `-0.015em` headings;
  `0.12em`/`0.16em` on uppercase mono labels.

Spacing scale (px observed): 7, 9, 11, 14, 16, 18, 20, 22, 26, 28, 30, 40, 56.
Border radius: **0** on all containers/controls; `999px` only on circular badges/dots.
Shadows:
- Button primary: `0 1px 2px rgba(60,64,67,.18)`; hover `0 1px 3px rgba(60,64,67,.3), 0 4px 8px 3px rgba(60,64,67,.15)`
- Translated card: `0 1px 2px rgba(60,64,67,.08), 0 2px 8px 2px color-mix(in srgb, var(--accent) 8%, transparent)`

Tweakable props (from the prototype, worth exposing as settings/variants):
- `accent` (color), `paneLayout` ("Side by side" → flex-row / "Stacked" → flex-column),
  `showPageMarkers` (boolean).

## Assets
- No raster images. All icons are inline SVG (stroke ~1.6–1.9, `currentColor`): upload-arrow,
  clock-history, chevron-down, swap (two-arrows), arrow-right, download, checkmark, file/document.
  Replace with the codebase's existing icon set (Material Symbols, Lucide, etc.).
- Wordmark glyph is the literal character "文" (no image asset).
- Fonts load from Google Fonts in the prototype; use the codebase's font pipeline.

## Files
- `PDF Translator.dc.html` — the high-fidelity design reference (this bundle).
- Original starting point for context: the app was a single page titled "PDF Translator" with a
  dashed dropzone, From/To selects + Translate button, an error/status box, and ORIGINAL/TRANSLATED
  panes. This redesign preserves that layout and structure.
