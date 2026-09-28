"""The pods CLI side of the command socket. Stdlib only, so it starts fast."""
import os
import socket

COMMANDS = ("anc", "transparency", "adaptive", "off", "battery", "status", "ear")
EAR_WORDS = ("on", "off")  # `pods ear on|off`; bare `pods ear` just shows it
NOT_RUNNING = "pods isn't running (start it with: systemctl --user start pods)"


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(runtime, "pods.sock")


def ask(path, line, timeout=5):
    """Send one command, return (ok, reply text)."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(path)
            s.sendall(line.encode() + b"\n")
            chunks = []
            while chunk := s.recv(4096):
                chunks.append(chunk)
    except (FileNotFoundError, ConnectionRefusedError):
        return False, NOT_RUNNING
    except TimeoutError:
        return False, "pods didn't answer"
    # Reply is "ok\n<text>" or "error\n<text>".
    status, _, text = b"".join(chunks).decode().partition("\n")
    return status == "ok", text.rstrip("\n")
