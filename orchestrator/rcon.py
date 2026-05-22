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

    def dumpuser(self, slot: int) -> dict[str, str]:
        """Parse dumpuser output into lowercase keys."""
        out = self.command(f"dumpuser {slot}")
        data: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                data[k.strip().lower()] = v.strip().strip('"')
            else:
                m = re.match(r"^user\s+(\d+):", line, re.I)
                if m:
                    data["slot"] = m.group(1)
        return data

    def all_userinfo(self, max_slots: int = 16) -> list[dict[str, str]]:
        users = []
        for slot in range(max_slots):
            info = self.dumpuser(slot)
            if info.get("name") or info.get("ladder_uid") or info.get("ip"):
                info["slot"] = str(slot)
                users.append(info)
        return users
