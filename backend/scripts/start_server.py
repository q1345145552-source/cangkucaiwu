"""Resolve Docker nginx to exact trusted IPs before starting Uvicorn 0.30.6."""
import os
import socket
import sys
import time
from ipaddress import ip_address


def resolve_proxy_ips(hosts, extra_ips="", attempts=40):
    trusted = {str(ip_address(value.strip())) for value in extra_ips.split(",") if value.strip()}
    for host in (value.strip() for value in hosts.split(",") if value.strip()):
        if host == "*" or "/" in host:
            raise ValueError("受信任代理必须是明确的主机名或 IP，不能信任所有来源或整个网段")
        try:
            trusted.add(str(ip_address(host)))
            continue
        except ValueError:
            pass
        for attempt in range(attempts):
            try:
                addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                resolved = {str(ip_address(address[4][0])) for address in addresses}
                if not resolved:
                    raise OSError("empty proxy address list")
                trusted.update(resolved)
                break
            except OSError:
                if attempt + 1 == attempts:
                    raise RuntimeError(f"无法解析受信任代理 {host}，拒绝以信任所有来源的方式启动") from None
                time.sleep(0.5)
    return ",".join(sorted(trusted))


def main():
    os.environ["FORWARDED_ALLOW_IPS"] = resolve_proxy_ips(
        os.environ.get("TRUSTED_PROXY_HOSTS", ""), os.environ.get("FORWARDED_ALLOW_IPS", ""),
    )
    print(f"Uvicorn 代理头已启用，可信代理 IP：{os.environ['FORWARDED_ALLOW_IPS'] or '(无，忽略代理头)'}", flush=True)
    # The same allow-list is inherited by the app's X-Real-IP fallback helper.
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", *sys.argv[1:]])


if __name__ == "__main__":
    main()
