import threading
import webbrowser

import uvicorn

from .app import app

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    url = f"http://{HOST}:{PORT}"
    # Open the browser shortly after the server starts accepting connections.
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
