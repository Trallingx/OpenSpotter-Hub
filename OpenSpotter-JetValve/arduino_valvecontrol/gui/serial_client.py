import serial
from serial.tools import list_ports


class SerialClient:
    def __init__(self, port: str, baud: int = 9600):
        self.port = port
        self.baud = baud
        self.ser = serial.Serial(port, baudrate=baud, timeout=0)
        self._rx_buffer = ""

    @staticmethod
    def available_ports():
        return [p.device for p in list_ports.comports()]

    @staticmethod
    def find_best_port():
        ports = list(list_ports.comports())
        if not ports:
            return None

        def score(port_info) -> int:
            text = " ".join(
                [
                    port_info.device or "",
                    getattr(port_info, "description", "") or "",
                    getattr(port_info, "manufacturer", "") or "",
                    getattr(port_info, "product", "") or "",
                    getattr(port_info, "hwid", "") or "",
                ]
            ).lower()

            s = 0
            if "arduino" in text:
                s += 120
            if "ch340" in text or "wch" in text:
                s += 80
            if "cp210" in text or "silicon labs" in text:
                s += 80
            if "usb serial" in text or "usb-serial" in text:
                s += 40
            if "com" in (port_info.device or "").lower():
                s += 5
            return s

        best = max(ports, key=score)
        return best.device

    def write_line(self, line: str):
        if not line.endswith("\n"):
            line = line + "\n"
        self.ser.write(line.encode("ascii", errors="ignore"))

    def read_lines(self):
        waiting = self.ser.in_waiting
        if waiting <= 0:
            return []

        chunk = self.ser.read(waiting)
        if not chunk:
            return []

        self._rx_buffer += chunk.decode("ascii", errors="ignore")
        parts = self._rx_buffer.split("\n")
        self._rx_buffer = parts.pop()

        lines = []
        for line in parts:
            clean = line.strip("\r")
            if clean:
                lines.append(clean)
        return lines

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def is_open(self):
        return self.ser.is_open
