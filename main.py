"""
ViewNet — Mapeador de Red Empresarial
Detecta VLAN, switch y puerto desde cualquier toma RJ45.

Uso:
    python main.py          → Abre la interfaz gráfica
    python main.py --cli    → Modo terminal
"""
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _run_gui():
    from ui.gui_app import ViewNetApp
    app = ViewNetApp()
    app.mainloop()


def _run_cli():
    import argparse
    from core.iface_selector import list_physical_interfaces
    from core.lldp_listener import start_listen
    from core.snmp_discovery import enrich_snmp
    import threading
    import time

    parser = argparse.ArgumentParser(description="ViewNet CLI")
    parser.add_argument("--iface",     default=None)
    parser.add_argument("--community", default="public")
    parser.add_argument("--timeout",   default=90, type=int)
    args = parser.parse_args()

    print("\n  ViewNet — Mapeador de Red Empresarial")
    print("  =" * 30)

    ifaces = list_physical_interfaces()
    if not ifaces:
        print("  ERROR: No se encontraron interfaces.")
        sys.exit(1)

    iface = args.iface
    if not iface:
        print("\n  Interfaces disponibles:")
        for i, ifc in enumerate(ifaces, 1):
            print(f"    [{i}] {ifc['name']}  ({ifc['ip']})")
        choice = input("\n  Seleccioná una [1]: ").strip() or "1"
        iface = ifaces[int(choice) - 1]["name"]

    print(f"\n  Interfaz: {iface}")
    print(f"  Esperando LLDP/CDP (timeout: {args.timeout}s)...\n")

    found = threading.Event()
    result = [None]

    def on_found(port):
        result[0] = port
        found.set()

    def on_log(msg):
        print(f"  {msg}")

    stop = start_listen(iface, args.timeout, on_found, on_log)
    found.wait(timeout=args.timeout + 5)

    port = result[0]
    if not port:
        print("\n  Sin respuesta.")
        sys.exit(1)

    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  RESULTADO DEL ESCANEO                   ║")
    print(f"  ╠══════════════════════════════════════════╣")
    print(f"  ║  Protocolo : {port.protocol:<28} ║")
    print(f"  ║  Switch    : {port.display_switch():<28} ║")
    print(f"  ║  IP Switch : {port.switch_ip or 'N/D':<28} ║")
    print(f"  ║  Puerto    : {port.display_port():<28} ║")
    print(f"  ║  VLAN      : {port.display_vlan():<28} ║")
    print(f"  ╚══════════════════════════════════════════╝\n")

    if port.switch_ip:
        print("  Enriqueciendo con SNMP...")
        enrich_snmp(port, args.community, on_log)
        print(f"  VLAN nombre : {port.vlan_name or 'N/D'}")
        print(f"  Descripción : {port.display_description()}")
        print(f"  Modelo      : {port.switch_model[:60] if port.switch_model else 'N/D'}")


if __name__ == "__main__":
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        _run_cli()
    else:
        _run_gui()
