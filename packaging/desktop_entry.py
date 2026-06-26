"""Entry point for the packaged desktop build.

PyInstaller needs a plain script to bundle. This just hands off to the existing
launcher, which starts the local server and opens the browser.
"""
from pdftranslator.web.__main__ import main

if __name__ == "__main__":
    main()
