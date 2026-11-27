import argparse
import ipaddress
import socket
import time

parser = argparse.ArgumentParser(description="Count 32 nonce-tagged UDP datagrams from a test client")
parser.add_argument("client_ipv4", type=ipaddress.IPv4Address)
parser.add_argument("port", type=int)
parser.add_argument("size", type=int, choices=(128, 1024))
parser.add_argument("token_hex")
args = parser.parse_args()
if not 1 <= args.port <= 65535:
    parser.error("port must be between 1 and 65535")
try:
    token = bytes.fromhex(args.token_hex)
except ValueError:
    parser.error("token_hex must be 16 bytes in hex")
if len(token) != 16:
    parser.error("token_hex must be 16 bytes in hex")

received = 0
deadline = time.monotonic() + 25
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
    receiver.bind(("0.0.0.0", args.port))
    print("ready", flush=True)
    while received < 32:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        receiver.settimeout(remaining)
        try:
            datagram, peer = receiver.recvfrom(2048)
        except socket.timeout:
            break
        if peer[0] == str(args.client_ipv4) and len(datagram) == args.size and datagram.startswith(token):
            received += 1
            receiver.sendto(b"ok" + token, peer)

print(f"{received} datagrams, {received * args.size} bytes")
raise SystemExit(0 if received == 32 else 1)
