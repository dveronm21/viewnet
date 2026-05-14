"""
Escucha pasiva de paquetes LLDP (802.1AB) y CDP (Cisco) en la interfaz física.
El switch los emite automáticamente cada 30 segundos.
Requiere: Npcap en Windows, o permisos root en Linux.
"""
import struct
import time
import threading
from typing import Optional, Callable
from models.port_info import DiscoveredPort

# MACs de multicast para LLDP y CDP
LLDP_MULTICAST = "01:80:c2:00:00:0e"
CDP_MULTICAST  = "01:00:0c:cc:cc:cc"

# Ethertype LLDP
ETH_LLDP = 0x88CC


# ─────────────────────────────────────────────
#  Parsers de paquetes
# ─────────────────────────────────────────────

def _safe_decode(b: bytes) -> str:
    """Decodifica bytes descartando caracteres inválidos y nulos finales."""
    s = b.decode("utf-8", errors="ignore").rstrip("\x00").strip()
    # Quitar también caracteres de control que rompen terminales
    return "".join(c for c in s if c.isprintable() or c in "\t ")


def _parse_lldp_raw(data: bytes) -> DiscoveredPort:
    """Parsea un frame LLDP crudo y extrae todos los TLVs relevantes."""
    info = DiscoveredPort(protocol="LLDP")
    i = 14  # saltar cabecera Ethernet (6+6+2)

    while i < len(data) - 2:
        try:
            hdr = struct.unpack("!H", data[i:i+2])[0]
            tlv_type = (hdr >> 9) & 0x7F
            tlv_len  = hdr & 0x01FF
            i += 2
            if tlv_type == 0:        # End of LLDPDU
                break
            payload = data[i:i+tlv_len]
            i += tlv_len

            if tlv_type == 1:        # Chassis ID
                subtype = payload[0] if payload else 0
                body = payload[1:]
                if subtype == 4 and len(body) >= 6:        # MAC
                    val = ":".join(f"{b:02x}" for b in body[:6])
                elif subtype == 5 and len(body) >= 5:      # Network address
                    family = body[0]
                    if family == 1 and len(body) >= 5:
                        val = ".".join(str(b) for b in body[1:5])
                    else:
                        val = body[1:].hex()
                else:
                    val = _safe_decode(body)
                info.chassis_id = val

            elif tlv_type == 2:      # Port ID
                subtype = payload[0] if payload else 0
                body = payload[1:]
                if subtype == 3 and len(body) >= 6:        # MAC address
                    info.local_port = ":".join(f"{b:02x}" for b in body[:6])
                elif subtype == 4 and len(body) >= 5:      # Network address
                    family = body[0]
                    if family == 1 and len(body) >= 5:     # IPv4
                        info.local_port = ".".join(str(b) for b in body[1:5])
                    else:
                        info.local_port = body[1:].hex()
                else:                                      # 1,2,5,6,7 = string
                    info.local_port = _safe_decode(body)

            elif tlv_type == 4:      # Port Description
                info.port_description = _safe_decode(payload)

            elif tlv_type == 5:      # System Name
                info.switch_name = _safe_decode(payload)

            elif tlv_type == 6:      # System Description
                info.switch_model = _safe_decode(payload)[:120]

            elif tlv_type == 8:      # Management Address
                if len(payload) >= 2:
                    addr_len     = payload[0]   # incluye el byte de subtype
                    addr_subtype = payload[1] if addr_len >= 1 else 0
                    if addr_subtype == 1 and addr_len == 5 and len(payload) >= 6:
                        # IPv4 — preferida; siempre sobreescribe
                        info.switch_ip = ".".join(str(b) for b in payload[2:6])
                    elif addr_subtype == 2 and addr_len == 17 and len(payload) >= 18:
                        # IPv6 — solo si aún no hay IPv4
                        if not info.switch_ip:
                            info.switch_ip = ":".join(
                                f"{payload[2+i]:02x}{payload[3+i]:02x}"
                                for i in range(0, 16, 2)
                            )

            elif tlv_type == 127:    # Organizationally Specific
                if len(payload) >= 4:
                    oui     = payload[:3]
                    subtype = payload[3]
                    # IEEE 802.1Q — Port VLAN ID (OUI: 00-80-C2, sub: 1)
                    if oui == b'\x00\x80\xc2' and subtype == 0x01 and len(payload) >= 6:
                        info.vlan_id = struct.unpack("!H", payload[4:6])[0]
                    # IEEE 802.1Q — VLAN Name (OUI: 00-80-C2, sub: 3)
                    elif oui == b'\x00\x80\xc2' and subtype == 0x03 and len(payload) >= 7:
                        vlan_id   = struct.unpack("!H", payload[4:6])[0]
                        name_len  = payload[6]
                        vlan_name = _safe_decode(payload[7:7+name_len])
                        if info.vlan_id == vlan_id or not info.vlan_id:
                            info.vlan_name = vlan_name

        except Exception:
            break

    return info


def _parse_cdp_raw(data: bytes) -> DiscoveredPort:
    """Parsea un frame CDP crudo (Cisco proprietary)."""
    info = DiscoveredPort(protocol="CDP")

    # CDP va sobre LLC/SNAP: Ethernet + 8 bytes LLC/SNAP + 4 bytes CDP header
    # Offset aproximado: 14 (eth) + 8 (llc/snap) + 4 (cdp ver+ttl+checksum) = 26
    i = 26
    while i < len(data) - 4:
        try:
            t, l = struct.unpack("!HH", data[i:i+4])
            if l < 4 or i + l > len(data):
                break
            val = data[i+4:i+l]

            if t == 0x0001:      # Device ID
                info.switch_name = _safe_decode(val)
            elif t == 0x0002:    # Addresses
                if len(val) >= 4:
                    num_addr = struct.unpack("!I", val[:4])[0]
                    pos = 4
                    for _ in range(min(num_addr, 5)):
                        if pos + 4 > len(val):
                            break
                        proto_type = val[pos]
                        proto_len  = val[pos+1]
                        pos += 2 + proto_len
                        if pos + 2 > len(val):
                            break
                        addr_len = struct.unpack("!H", val[pos:pos+2])[0]
                        pos += 2
                        if proto_type == 1 and addr_len == 4:   # IPv4
                            info.switch_ip = ".".join(str(b) for b in val[pos:pos+4])
                        pos += addr_len
            elif t == 0x0003:    # Port ID
                info.local_port = _safe_decode(val)
            elif t == 0x0005:    # Software Version
                info.switch_model = _safe_decode(val)[:120]
            elif t == 0x0006:    # Platform
                info.switch_model = _safe_decode(val)[:80]
            elif t == 0x000A:    # Native VLAN
                if len(val) >= 2:
                    info.vlan_id = struct.unpack("!H", val[:2])[0]

            i += l
        except Exception:
            break

    return info


# ─────────────────────────────────────────────
#  Listener principal con Scapy
# ─────────────────────────────────────────────

def _resolve_iface(iface: str, on_log: Callable) -> str:
    # En Windows convierte nombre amigable → GUID Npcap si es necesario.
    # Si ya es un GUID (Device/NPF_) lo devuelve tal cual.
    if iface.startswith(r"\Device\NPF_"):
        return iface   # ya es GUID, listo

    # En Windows, buscar en IFACES de Scapy por nombre
    try:
        from scapy.all import IFACES
        for guid, obj in IFACES.items():
            if getattr(obj, "name", "") == iface:
                on_log(f"Npcap: '{iface}' → {guid}")
                return guid
    except Exception:
        pass
    return iface


def _scapy_listen(iface: str, timeout: int,
                  on_found: Callable, on_log: Callable, stop_evt: threading.Event):
    """
    Escucha con AsyncSniffer para que el botón "Detener" responda
    inmediatamente aunque no lleguen paquetes.
    """
    try:
        from scapy.all import AsyncSniffer, Ether, conf
        conf.verb = 0

        iface_resolved = _resolve_iface(iface, on_log)
        on_log(f"Capturando en: {iface_resolved}")

        found_count = [0]

        def handle(pkt):
            # BLINDAJE: jamás permitir que una excepción escape al socket Scapy
            try:
                if Ether not in pkt:
                    return
                dst = pkt[Ether].dst.lower()
                raw = bytes(pkt)
                info = None

                if dst == LLDP_MULTICAST:
                    try: on_log("Paquete LLDP recibido, parseando...")
                    except Exception: pass
                    info = _parse_lldp_raw(raw)
                elif dst == CDP_MULTICAST:
                    try: on_log("Paquete CDP recibido, parseando...")
                    except Exception: pass
                    info = _parse_cdp_raw(raw)

                if info:
                    if info.switch_name:
                        stop_evt.set()
                        try: on_found(info)
                        except Exception as e:
                            try: on_log(f"on_found error: {e}")
                            except Exception: pass
                    else:
                        found_count[0] += 1
                        try: on_log(f"Frame recibido ({found_count[0]}) sin nombre, esperando más...")
                        except Exception: pass
            except Exception as e:
                try: on_log(f"Error en handler: {type(e).__name__}: {e}")
                except Exception: pass

        bpf = "ether dst 01:80:c2:00:00:0e or ether dst 01:00:0c:cc:cc:cc"
        sniffer = AsyncSniffer(
            iface=iface_resolved, filter=bpf, prn=handle, store=False
        )
        sniffer.start()

        # Loop con polling de stop_evt cada 300ms
        deadline = time.time() + timeout
        while time.time() < deadline and not stop_evt.is_set():
            time.sleep(0.3)

        if sniffer.running:
            try:
                sniffer.stop()
            except Exception:
                pass

    except Exception as e:
        on_log(f"[Scapy/Npcap] Error: {e}")
        import traceback
        on_log(traceback.format_exc().splitlines()[-1])


def _raw_socket_listen(iface: str, timeout: int,
                       on_found: Callable, on_log: Callable, stop_evt: threading.Event):
    """
    Fallback: escucha con raw socket de Python (solo Linux).
    En Windows sin Npcap usa esta ruta.
    """
    import socket as _socket
    try:
        sock = _socket.socket(_socket.AF_PACKET, _socket.SOCK_RAW,
                              _socket.htons(0x0003))
        sock.bind((iface, 0))
        sock.settimeout(2.0)
        deadline = time.time() + timeout

        while time.time() < deadline and not stop_evt.is_set():
            try:
                data, _ = sock.recvfrom(65535)
                if len(data) < 14:
                    continue
                dst_mac = ":".join(f"{b:02x}" for b in data[:6])
                ethertype = struct.unpack("!H", data[12:14])[0]
                info = None
                if dst_mac == LLDP_MULTICAST and ethertype == ETH_LLDP:
                    info = _parse_lldp_raw(data)
                elif dst_mac == CDP_MULTICAST:
                    info = _parse_cdp_raw(data)
                if info and info.switch_name:
                    stop_evt.set()
                    on_found(info)
                    break
            except _socket.timeout:
                continue
        sock.close()
    except PermissionError:
        on_log("Sin permisos para raw socket. Ejecuta como Administrador.")
    except Exception as e:
        on_log(f"[RawSocket] Error: {e}")


# ─────────────────────────────────────────────
#  API pública
# ─────────────────────────────────────────────

def start_listen(iface: str, timeout: int,
                 on_found: Callable[[DiscoveredPort], None],
                 on_log: Callable[[str], None]) -> threading.Event:
    """
    Inicia la escucha de LLDP/CDP en un hilo separado.
    Retorna el evento de parada (llámalo con .set() para cancelar).
    """
    stop_evt = threading.Event()

    def worker():
        on_log(f"Iniciando captura (timeout: {timeout}s)...")
        on_log("Los switches envían LLDP/CDP cada ~30 segundos.")

        try:
            from scapy.all import conf as _conf
            _conf.verb = 0
            on_log("Backend: Scapy + Npcap [OK]")
            _scapy_listen(iface, timeout, on_found, on_log, stop_evt)
        except ImportError:
            on_log("Scapy no disponible — usando raw socket (solo Linux)...")
            _raw_socket_listen(iface, timeout, on_found, on_log, stop_evt)

        if not stop_evt.is_set():
            on_log("Timeout: no se detectó respuesta LLDP/CDP.")
            on_log("¿LLDP habilitado en el switch? → 'lldp run' (Cisco)")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return stop_evt
