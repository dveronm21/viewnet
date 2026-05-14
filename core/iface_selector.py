"""
Detección de interfaces de red con soporte completo para Npcap (Windows).
Mapea nombres amigables → GUIDs de Npcap que Scapy puede usar directamente.
"""
import socket
import psutil
import platform

# Adaptadores virtuales/irrelevantes que se descartan
_SKIP_DESCRIPTIONS = (
    "WAN Miniport",
    "Loopback",
    "Pseudo-Interface",
    "Hyper-V Virtual",
    "Microsoft Wi-Fi Direct Virtual",
    "TAP-Windows",
    "Software Loopback",
)
_SKIP_NAME_PREFIXES = ("lo", "veth", "docker", "virbr", "br-", "vmnet")


def _build_npcap_map() -> dict[str, str]:
    """
    Retorna {nombre_amigable: guid_npcap} usando el objeto IFACES de Scapy.
    Solo disponible en Windows con Npcap instalado.
    """
    try:
        from scapy.all import IFACES
        result = {}
        for guid, iface_obj in IFACES.items():
            name = getattr(iface_obj, "name", None)
            desc = (getattr(iface_obj, "description", None) or
                    getattr(iface_obj, "friendlyname", None) or "")
            if not name:
                continue
            # Descartar adaptadores virtuales por descripción
            if any(skip.lower() in desc.lower() for skip in _SKIP_DESCRIPTIONS):
                continue
            result[name] = guid
        return result
    except ImportError:
        return {}


def list_physical_interfaces() -> list[dict]:
    """
    Retorna lista de interfaces físicas con:
      - name    : nombre amigable (para mostrar)
      - ip      : dirección IPv4
      - guid    : GUID Npcap (para pasar a Scapy en Windows)
      - up      : si está activa
      - desc    : descripción del adaptador
    """
    npcap_map = _build_npcap_map()
    skip_prefixes = tuple(_SKIP_NAME_PREFIXES)

    stats  = psutil.net_if_stats()
    addrs  = psutil.net_if_addrs()
    result = []

    for name, addr_list in addrs.items():
        lower = name.lower()
        if any(lower.startswith(p) for p in skip_prefixes):
            continue
        if "loopback" in lower or "vethernet" in lower.replace(" ", ""):
            continue

        iface_stats = stats.get(name)
        ip = ""
        for addr in addr_list:
            if addr.family == socket.AF_INET:
                ip = addr.address
                break

        guid = npcap_map.get(name, name)   # fallback al nombre si no hay GUID

        # En Windows con Npcap disponible, solo mostrar interfaces que Npcap vea
        # Si npcap_map está vacío (Scapy no instalado), no filtrar por GUID
        is_windows = platform.system() == "Windows"
        if is_windows and npcap_map and name not in npcap_map:
            continue

        result.append({
            "name"  : name,
            "ip"    : ip or "Sin IP",
            "guid"  : guid,
            "up"    : iface_stats.isup if iface_stats else False,
            "speed" : getattr(iface_stats, "speed", 0) if iface_stats else 0,
        })

    # Ordenar: activas con IP primero
    result.sort(key=lambda x: (not x["up"], x["ip"] == "Sin IP", x["name"]))
    return result
