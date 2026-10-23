from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "bitclient-single-instance"


class InstanceServer(QObject):
    received = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self.on_connection)

    def listen(self) -> bool:
        QLocalServer.removeServer(SERVER_NAME)
        return self.server.listen(SERVER_NAME)

    def on_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return
        socket.waitForReadyRead(1500)
        data = bytes(socket.readAll()).decode("utf-8", errors="ignore")
        socket.disconnectFromServer()
        self.received.emit([line for line in data.split("\n") if line])


def forward_to_running(arguments: list) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(500):
        return False
    payload = "\n".join(arguments) if arguments else "\n"
    socket.write(payload.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1500)
    socket.disconnectFromServer()
    return True
