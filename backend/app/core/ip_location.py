"""Offline audit-log geolocation. The bundled DB is loaded once per process."""
import gzip
import ipaddress
import logging
from pathlib import Path
from threading import Lock

import maxminddb

logger = logging.getLogger("uvicorn.error")
DATABASE = Path(__file__).resolve().parents[2] / "data/geoip/dbip-city-lite-2026-10.mmdb.gz"
_reader = None
_loaded = False
_load_lock = Lock()
_PRIVATE = tuple(map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")))

# Display translations only; IP ranges and their locations always come from DB-IP.
_ZH = {
    "Beijing": "北京", "Tianjin": "天津", "Hebei": "河北", "Shanxi": "山西",
    "Inner Mongolia": "内蒙古", "Liaoning": "辽宁", "Jilin": "吉林", "Heilongjiang": "黑龙江",
    "Shanghai": "上海", "Jiangsu": "江苏", "Zhejiang": "浙江", "Anhui": "安徽",
    "Fujian": "福建", "Jiangxi": "江西", "Shandong": "山东", "Henan": "河南",
    "Hubei": "湖北", "Hunan": "湖南", "Guangdong": "广东", "Guangxi": "广西",
    "Hainan": "海南", "Chongqing": "重庆", "Sichuan": "四川", "Guizhou": "贵州",
    "Yunnan": "云南", "Tibet": "西藏", "Shaanxi": "陕西", "Gansu": "甘肃",
    "Qinghai": "青海", "Ningxia": "宁夏", "Xinjiang": "新疆", "Taiwan": "台湾",
    "Hong Kong": "香港", "Macao": "澳门", "Guangzhou": "广州", "Shenzhen": "深圳",
    "Hangzhou": "杭州", "Chengdu": "成都", "Wuhan": "武汉", "Nanjing": "南京",
    "Bangkok": "曼谷", "Wang Thonglang": "旺通朗",
}


def _database():
    global _reader, _loaded
    with _load_lock:
        if not _loaded:
            try:
                # MODE_FD reads the decompressed stream entirely into memory.
                # The gzip/file handle closes immediately, never used per lookup.
                with gzip.open(DATABASE, "rb") as stream:
                    _reader = maxminddb.open_database(stream, mode=maxminddb.MODE_FD)
            except Exception:
                logger.warning("离线IP地区库加载失败，地区将显示未知")
            _loaded = True
    return _reader


def _name(record):
    names = (record or {}).get("names") or {}
    name = names.get("zh-CN") or names.get("en") or ""
    return _ZH.get(name, name)


def get_ip_location(value):
    """Return country/region/city strings; failures and unknown IPs return empty strings."""
    empty = {"ip_country": "", "ip_region": "", "ip_city": ""}
    try:
        ip = ipaddress.ip_address(value)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if ip.is_unspecified or ip.is_multicast:
            return empty
        if ip.is_loopback or ip.is_link_local or any(ip.version == net.version and ip in net for net in _PRIVATE):
            return {**empty, "ip_country": "内网"}
        if not ip.is_global:
            return empty
        reader = _database()
        data = reader.get(str(ip)) if reader else None
        if not data:
            return empty
        subdivisions = data.get("subdivisions") or []
        return {
            "ip_country": _name(data.get("country")),
            "ip_region": _name(subdivisions[0]) if subdivisions else "",
            "ip_city": _name(data.get("city")),
        }
    except Exception:
        return empty
