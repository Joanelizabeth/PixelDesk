"""Ensures only one Pixel Desk runs per user; a second launch shows the first."""
from __future__ import annotations

import getpass
import logging
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover
        user = "user"
    return "PixelDesk-" + re.sub(r"[^A-Za-z0-9_-]", "_", user)


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, name: str | None = None, parent=None):
        super().__init__(parent)
        self.name = name or _server_name()
        self._server: QLocalServer | None = None

    def already_running(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if sock.waitForConnected(400):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(400)
            sock.disconnectFromServer()
            return True
        return False

    def listen(self) -> bool:
        self._server = QLocalServer(self)
        if not self._server.listen(self.name):
            # A stale socket from a crashed instance: remove and retry.
            QLocalServer.removeServer(self.name)
            if not self._server.listen(self.name):
                log.warning("Single-instance server could not listen: %s", self._server.errorString())
                return False
        self._server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(lambda: (conn.readAll(), self.activated.emit()))
            conn.disconnected.connect(conn.deleteLater)

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
