# Download & run pdfTranslator

pdfTranslator ships as a single download per platform. It runs entirely on your
own computer — your PDFs and any API key never leave your machine — and opens in
your web browser.

## Get the app

1. Go to the **[Releases](../../releases)** page of this repository.
2. Download the file for your system from the latest release:
   - **Windows** → `pdfTranslator-windows.exe`
   - **macOS** → `pdfTranslator-macos.zip` (unzip to get `pdfTranslator.app`)

## Run it

- **Windows:** double-click `pdfTranslator-windows.exe`.
- **macOS:** unzip, then double-click `pdfTranslator.app`.

A small status window opens and your browser launches at
`http://127.0.0.1:8000`. Translate from there. **Closing the status window quits
the app.**

## First-launch security warning (expected)

The apps are not code-signed, so the OS shows a one-time warning. This is normal
for indie tools; you only need to do this once per download.

- **Windows — "Windows protected your PC" (SmartScreen):**
  click **More info** → **Run anyway**.
- **macOS — "cannot be opened because it is from an unidentified developer":**
  right-click (or Control-click) `pdfTranslator.app` → **Open** → **Open**.
  If macOS still blocks it, go to **System Settings → Privacy & Security** and
  click **Open Anyway**.

## Using an LLM engine (optional)

The default **Google** engine needs no setup. To use **Claude** or **ChatGPT**,
pick that engine in the app and paste your own API key when prompted. The key is
saved locally on your machine (`~/.config/pdftranslator/config.json`) and is used
only for your translations.

## Building it yourself

PyInstaller cannot cross-compile, so each binary is built on its own OS:

```bash
pip install . pyinstaller
pyinstaller --noconfirm --clean packaging/pdftranslator.spec
# → dist/pdfTranslator.exe (Windows) or dist/pdfTranslator.app (macOS)
```

CI builds both automatically — see `.github/workflows/build-desktop.yml`. Pushing
a version tag publishes a Release with both binaries attached:

```bash
git tag v0.1.0 && git push origin v0.1.0
```
