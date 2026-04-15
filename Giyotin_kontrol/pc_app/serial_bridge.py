import time
import serial
from serial.tools import list_ports


def list_serial_ports():
    return [port.device for port in list_ports.comports()]

class NanoGiyotin:
    def __init__(self, port: str = "COM12", baud: int = 9600, timeout: float = 0.2):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        # Nano reset olur, biraz bekle
        time.sleep(2.0)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def write_cmd(self, cmd: str):
        self.ser.write((cmd.strip() + "\n").encode("utf-8"))
        self.ser.flush()

    def read_line(self) -> str:
        try:
            return self.ser.readline().decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass
