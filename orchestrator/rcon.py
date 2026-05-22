import re
import socket


def _packet(cmd: str) -> bytes:
    return b"\xff\xff\xff\xff" + cmd.encode("latin-1", errors="replace") + b"\n"


class QuakeRcon:
    def __init__(self, host: str, port: int, password: str, timeout: float = 2.0):
        self.addr = (host, port)
        self.password = password
        self.timeout = timeout

    def _send_recv(self, data: bytes) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(data, self.addr)
            chunks = []
            for _ in range(8):
                try:
                    buf, _ = sock.recvfrom(4096)
                    if len(buf) >= 5 and buf[:4] == b"\xff\xff\xff\xff":
                        chunks.append(buf[4:].decode("latin-1", errors="replace"))
                except socket.timeout:
                    break
            return "".join(chunks)
        finally:
            sock.close()

    def command(self, cmd: str) -> str:
        challenge = self._send_recv(_packet("challenge rcon"))
        m = re.search(r"challenge\s+(\S+)", challenge)
        if not m:
            return challenge
        ch = m.group(1)
        payload = _packet(f"rcon {ch} {self.password} {cmd}")
        return self._send_recv(payload)

    def players_status(self) -> list[dict]:
        """Parse status output; fallback empty."""
        out = self.command("status")
        players = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("---") or "hostname" in line.lower():
                continue
            # slot name ... score ping
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                players.append({"slot": int(parts[0]), "name": parts[1], "raw": line})
        return players
