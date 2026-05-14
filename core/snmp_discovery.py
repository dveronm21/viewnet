"""
Enriquecimiento de datos via SNMP.
Consulta el switch para obtener nombre de VLAN, alias del puerto y modelo.
"""
import threading
from typing import Optional, Callable
from models.port_info import DiscoveredPort

# OIDs estándar MIB-II + 802.1Q
_OID_SYS_NAME    = "1.3.6.1.2.1.1.5.0"
_OID_SYS_DESCR   = "1.3.6.1.2.1.1.1.0"
_OID_IF_NAME     = "1.3.6.1.2.1.31.1.1.1.1"
_OID_IF_ALIAS    = "1.3.6.1.2.1.31.1.1.1.18"
_OID_IF_DESCR    = "1.3.6.1.2.1.2.2.1.2"
_OID_IF_PHYSADDR = "1.3.6.1.2.1.2.2.1.6"
_OID_DOT1Q_PVID  = "1.3.6.1.2.1.17.7.1.4.5.1.1"
_OID_VLAN_NAME   = "1.3.6.1.2.1.17.7.1.4.3.1.1"


def _looks_like_mac(s: str) -> bool:
    if not s:
        return False
    parts = s.split(":")
    return len(parts) == 6 and all(len(p) == 2 for p in parts)


def _normalize_mac(s: str) -> str:
    """Normaliza una MAC a formato 'aabbccddeeff' lowercase, sin separadores."""
    return "".join(c for c in s.lower() if c in "0123456789abcdef")


def _snmp_mac_value_to_hex(val: str) -> str:
    """
    pysnmp devuelve OctetString como repr; intenta extraer la MAC en hex.
    Acepta formas: '0x04eb40e37157', '04:eb:40:e3:71:57', o bytes crudos.
    """
    v = val.strip()
    if v.startswith("0x") or v.startswith("0X"):
        return v[2:].lower()
    if ":" in v or "-" in v:
        return _normalize_mac(v)
    # Repr binario tipo "\x04\xeb\x40..." → tomar solo hex chars
    hexed = "".join(f"{ord(c):02x}" for c in v) if len(v) == 6 else ""
    return hexed or _normalize_mac(v)


def _snmp_get(engine, community, target, ctx, oid: str) -> Optional[str]:
    from pysnmp.hlapi import getCmd, ObjectType, ObjectIdentity
    iterator = getCmd(engine, community, target, ctx,
                      ObjectType(ObjectIdentity(oid)))
    errInd, errStat, _, varBinds = next(iterator)
    if errInd or errStat:
        return None
    return str(varBinds[0][1]) if varBinds else None


def _snmp_walk(engine, community, target, ctx, oid: str) -> dict:
    from pysnmp.hlapi import nextCmd, ObjectType, ObjectIdentity
    results = {}
    for errInd, errStat, _, varBinds in nextCmd(
        engine, community, target, ctx,
        ObjectType(ObjectIdentity(oid)), lexicographicMode=False
    ):
        if errInd or errStat:
            break
        for vb in varBinds:
            key = str(vb[0])
            suffix = key.split(oid + ".")[-1] if oid in key else key
            results[suffix] = str(vb[1])
    return results


def enrich_snmp(port: DiscoveredPort, community: str,
                on_log: Callable[[str], None]) -> None:
    """
    Enriquece 'port' con datos SNMP. Modifica el objeto in-place.
    Diseñado para ejecutarse en un hilo separado.
    """
    if not port.switch_ip:
        on_log("Sin IP del switch, no se puede consultar SNMP.")
        return

    try:
        from pysnmp.hlapi import (
            SnmpEngine, CommunityData, UdpTransportTarget, ContextData
        )
    except ImportError:
        on_log("pysnmp no instalado — omitiendo enriquecimiento SNMP.")
        return

    on_log(f"Consultando SNMP en {port.switch_ip}...")
    try:
        engine  = SnmpEngine()
        comm    = CommunityData(community, mpModel=1)
        target  = UdpTransportTarget((port.switch_ip, 161), timeout=3, retries=1)
        ctx     = ContextData()

        # Nombre y modelo del switch
        sys_name  = _snmp_get(engine, comm, target, ctx, _OID_SYS_NAME)
        sys_descr = _snmp_get(engine, comm, target, ctx, _OID_SYS_DESCR)
        if sys_name:
            port.switch_name = port.switch_name or sys_name
        if sys_descr and not port.switch_model:
            port.switch_model = sys_descr[:120]

        # Mapa ifIndex ↔ ifName
        if_names = _snmp_walk(engine, comm, target, ctx, _OID_IF_NAME)
        if_index = None

        # Caso 1: el switch envió Port ID como MAC → resolver MAC → ifIndex → ifName
        if _looks_like_mac(port.local_port):
            on_log(f"Port ID es MAC ({port.local_port}); resolviendo vía ifPhysAddress...")
            target_mac = _normalize_mac(port.local_port)
            phys = _snmp_walk(engine, comm, target, ctx, _OID_IF_PHYSADDR)
            for idx, raw in phys.items():
                if _snmp_mac_value_to_hex(raw) == target_mac:
                    if_index = idx
                    real_name = if_names.get(idx, "")
                    if real_name:
                        on_log(f"MAC {port.local_port} → puerto {real_name}")
                        port.local_port = real_name
                    break
            if not if_index:
                on_log("No se encontró puerto con esa MAC en ifTable.")
                # Probar ifDescr como alternativa visual
                descrs = _snmp_walk(engine, comm, target, ctx, _OID_IF_DESCR)
                # nada que mapear sin index; seguimos
        else:
            # Caso 2: ya es nombre de interfaz; buscar por igualdad normalizada
            target_port = port.local_port.lower().replace("gigabitethernet", "gi") \
                                                 .replace("fastethernet", "fa") \
                                                 .replace("tengigabitethernet", "te")
            for idx, name in if_names.items():
                norm = name.lower().replace("gigabitethernet", "gi") \
                                   .replace("fastethernet", "fa") \
                                   .replace("tengigabitethernet", "te")
                if norm == target_port:
                    if_index = idx
                    break

        if if_index:
            # Alias del puerto (descripción administrativa)
            alias = _snmp_get(engine, comm, target, ctx,
                              f"{_OID_IF_ALIAS}.{if_index}")
            if alias:
                port.port_alias = alias

            # VLAN ID (dot1qPvid)
            pvid = _snmp_get(engine, comm, target, ctx,
                             f"{_OID_DOT1Q_PVID}.{if_index}")
            if pvid and pvid != "0":
                port.vlan_id = int(pvid)

        # Nombre de la VLAN
        if port.vlan_id:
            vlan_names = _snmp_walk(engine, comm, target, ctx, _OID_VLAN_NAME)
            vname = vlan_names.get(str(port.vlan_id), "")
            if vname:
                port.vlan_name = vname

        on_log("Información SNMP obtenida correctamente.")

    except Exception as e:
        on_log(f"SNMP error: {e}")


def start_snmp_enrich(port: DiscoveredPort, community: str,
                      on_log: Callable, on_done: Callable) -> None:
    """Lanza el enriquecimiento SNMP en un hilo separado."""
    def worker():
        enrich_snmp(port, community, on_log)
        on_done(port)

    threading.Thread(target=worker, daemon=True).start()
