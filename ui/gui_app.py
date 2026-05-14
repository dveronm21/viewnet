"""
ViewNet — Interfaz gráfica principal.
Construida con tkinter + ttk. Sin dependencias externas de UI.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import queue
import threading
import platform
import datetime

from core.iface_selector import list_physical_interfaces
from core.lldp_listener import start_listen
from core.snmp_discovery import start_snmp_enrich
from models.port_info import DiscoveredPort
from ui.topology_canvas import TopologyCanvas, vlan_color

# ─── Colores y fuentes ────────────────────────────────────────────────────────
BG_DARK    = "#0f1117"
BG_PANEL   = "#1e293b"
BG_CARD    = "#0f172a"
BG_INPUT   = "#1e293b"
FG_TEXT    = "#f1f5f9"
FG_MUTED   = "#94a3b8"
FG_GREEN   = "#10b981"
FG_BLUE    = "#3b82f6"
FG_YELLOW  = "#f59e0b"
FG_RED     = "#ef4444"
FG_PURPLE  = "#a78bfa"
ACCENT     = "#2563eb"
BTN_GREEN  = "#059669"
BTN_RED    = "#dc2626"

FONT_TITLE   = ("Segoe UI", 20, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_LABEL   = ("Segoe UI", 10)
FONT_VALUE   = ("Segoe UI", 10, "bold")
FONT_SMALL   = ("Segoe UI", 9)
FONT_MONO    = ("Consolas", 9)
FONT_LOG     = ("Consolas", 9)


def _hex_btn(master, text, command, bg, fg="white", width=14):
    """Botón con estilo flat personalizado."""
    btn = tk.Button(
        master, text=text, command=command,
        bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
        relief="flat", bd=0, cursor="hand2",
        font=("Segoe UI", 10, "bold"), width=width,
        padx=10, pady=8
    )
    return btn


class DetailRow(tk.Frame):
    """Fila etiqueta / valor con separador."""

    def __init__(self, parent, label: str, **kwargs):
        super().__init__(parent, bg=BG_CARD, **kwargs)
        self.label_w = tk.Label(self, text=label, font=FONT_LABEL,
                                fg=FG_MUTED, bg=BG_CARD, anchor="w", width=18)
        self.label_w.pack(side="left", padx=(0, 8))
        self.value_var = tk.StringVar(value="—")
        self.value_w = tk.Label(self, textvariable=self.value_var,
                                font=FONT_VALUE, fg=FG_TEXT, bg=BG_CARD,
                                anchor="w", wraplength=280)
        self.value_w.pack(side="left", fill="x", expand=True)

    def set(self, text: str, color: str = FG_TEXT):
        self.value_var.set(text)
        self.value_w.config(fg=color)


class ViewNetApp(tk.Tk):
    """Ventana principal de ViewNet."""

    def __init__(self):
        super().__init__()
        self.title("ViewNet — Mapeador de Red")
        self.configure(bg=BG_DARK)
        self.minsize(1050, 680)
        self.geometry("1200x750")
        self._center_window()

        # Estado interno
        self._stop_event: threading.Event | None = None
        self._msg_queue: queue.Queue = queue.Queue()
        self._scanning = False
        self._current_port: DiscoveredPort | None = None

        self._build_ui()
        self._populate_interfaces()
        self._poll_queue()

    # ─── Construcción de UI ───────────────────────────────────────────────────

    def _build_ui(self):
        # ── Barra de título ──────────────────────────────────────────────────
        title_bar = tk.Frame(self, bg="#0a0e1a", height=56)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        tk.Label(title_bar, text="⬡  ViewNet",
                 font=("Segoe UI", 18, "bold"), fg=FG_BLUE,
                 bg="#0a0e1a").pack(side="left", padx=20, pady=10)
        self._status_led = tk.Label(title_bar, text="●  Listo",
                                    font=FONT_SMALL, fg=FG_MUTED,
                                    bg="#0a0e1a")
        self._status_led.pack(side="left", padx=12)

        tk.Label(title_bar,
                 text="Mapeador de Red Empresarial  |  LLDP · CDP · SNMP",
                 font=FONT_SMALL, fg=FG_MUTED, bg="#0a0e1a"
                 ).pack(side="right", padx=20)

        # ── Cuerpo principal ─────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=12, pady=(8, 12))

        # Columna izquierda (controles + log)
        left = tk.Frame(body, bg=BG_DARK, width=280)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        self._build_config_panel(left)
        self._build_log_panel(left)

        # Columna derecha (topología + detalles)
        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side="left", fill="both", expand=True)

        self._build_topology_panel(right)
        self._build_details_panel(right)

    def _build_config_panel(self, parent):
        card = tk.Frame(parent, bg=BG_PANEL, bd=0)
        card.pack(fill="x", pady=(0, 8))

        tk.Label(card, text="CONFIGURACIÓN", font=FONT_SECTION,
                 fg=FG_BLUE, bg=BG_PANEL).pack(anchor="w", padx=14, pady=(12, 6))

        # Separador
        tk.Frame(card, bg=ACCENT, height=1).pack(fill="x", padx=14, pady=(0, 10))

        # Interfaz de red
        tk.Label(card, text="Interfaz de red", font=FONT_SMALL,
                 fg=FG_MUTED, bg=BG_PANEL).pack(anchor="w", padx=14)
        self._iface_var = tk.StringVar()
        iface_frame = tk.Frame(card, bg=BG_PANEL)
        iface_frame.pack(fill="x", padx=14, pady=(2, 8))
        self._iface_combo = ttk.Combobox(
            iface_frame, textvariable=self._iface_var,
            state="readonly", font=FONT_SMALL, width=22
        )
        self._iface_combo.pack(side="left", fill="x", expand=True)
        tk.Button(iface_frame, text="↺", font=("Segoe UI", 11),
                  command=self._populate_interfaces,
                  bg=BG_INPUT, fg=FG_BLUE, relief="flat",
                  cursor="hand2", padx=4).pack(side="left", padx=(4, 0))

        # Timeout
        tk.Label(card, text="Timeout (segundos)", font=FONT_SMALL,
                 fg=FG_MUTED, bg=BG_PANEL).pack(anchor="w", padx=14)
        self._timeout_var = tk.StringVar(value="90")
        tk.Entry(card, textvariable=self._timeout_var, font=FONT_SMALL,
                 bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief="flat", bd=4).pack(fill="x", padx=14, pady=(2, 8))

        # SNMP Community
        tk.Label(card, text="SNMP Community", font=FONT_SMALL,
                 fg=FG_MUTED, bg=BG_PANEL).pack(anchor="w", padx=14)
        self._snmp_var = tk.StringVar(value="public")
        tk.Entry(card, textvariable=self._snmp_var, font=FONT_SMALL,
                 bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief="flat", bd=4).pack(fill="x", padx=14, pady=(2, 8))

        # Sección SSH (colapsable)
        tk.Label(card, text="SSH (opcional)", font=FONT_SMALL,
                 fg=FG_MUTED, bg=BG_PANEL).pack(anchor="w", padx=14)
        tk.Frame(card, bg="#334155", height=1).pack(fill="x", padx=14, pady=(0, 6))

        tk.Label(card, text="Usuario", font=FONT_SMALL,
                 fg=FG_MUTED, bg=BG_PANEL).pack(anchor="w", padx=14)
        self._ssh_user = tk.StringVar()
        tk.Entry(card, textvariable=self._ssh_user, font=FONT_SMALL,
                 bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief="flat", bd=4).pack(fill="x", padx=14, pady=(2, 4))

        tk.Label(card, text="Contraseña", font=FONT_SMALL,
                 fg=FG_MUTED, bg=BG_PANEL).pack(anchor="w", padx=14)
        self._ssh_pass = tk.StringVar()
        tk.Entry(card, textvariable=self._ssh_pass, font=FONT_SMALL,
                 bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief="flat", bd=4, show="●").pack(fill="x", padx=14, pady=(2, 12))

        # Botones
        btn_frame = tk.Frame(card, bg=BG_PANEL)
        btn_frame.pack(fill="x", padx=14, pady=(0, 14))

        self._btn_scan = _hex_btn(btn_frame, "▶  Escanear",
                                  self._on_scan, BTN_GREEN)
        self._btn_scan.pack(fill="x", pady=(0, 6))

        self._btn_stop = _hex_btn(btn_frame, "■  Detener",
                                  self._on_stop, BTN_RED)
        self._btn_stop.pack(fill="x", pady=(0, 6))
        self._btn_stop.config(state="disabled")

        _hex_btn(btn_frame, "⊘  Limpiar",
                 self._on_clear, "#334155").pack(fill="x")

    def _build_log_panel(self, parent):
        card = tk.Frame(parent, bg=BG_PANEL)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=BG_PANEL)
        header.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(header, text="LOG DE ACTIVIDAD", font=FONT_SECTION,
                 fg=FG_BLUE, bg=BG_PANEL).pack(side="left")
        tk.Button(header, text="Limpiar", font=FONT_SMALL,
                  command=self._clear_log,
                  bg=BG_PANEL, fg=FG_MUTED, relief="flat",
                  cursor="hand2").pack(side="right")

        tk.Frame(card, bg=ACCENT, height=1).pack(fill="x", padx=14, pady=(0, 6))

        log_frame = tk.Frame(card, bg=BG_CARD)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        scroll = tk.Scrollbar(log_frame, bg=BG_CARD)
        scroll.pack(side="right", fill="y")

        self._log_text = tk.Text(
            log_frame, font=FONT_LOG, bg=BG_CARD, fg=FG_MUTED,
            insertbackground=FG_TEXT, relief="flat",
            wrap="word", yscrollcommand=scroll.set,
            state="disabled", padx=6, pady=6
        )
        self._log_text.pack(fill="both", expand=True)
        scroll.config(command=self._log_text.yview)

        # Tags de color para el log
        self._log_text.tag_config("info",    foreground=FG_MUTED)
        self._log_text.tag_config("success", foreground=FG_GREEN)
        self._log_text.tag_config("warning", foreground=FG_YELLOW)
        self._log_text.tag_config("error",   foreground=FG_RED)
        self._log_text.tag_config("ts",      foreground="#475569")

    def _build_topology_panel(self, parent):
        card = tk.Frame(parent, bg=BG_PANEL)
        card.pack(fill="both", expand=True, pady=(0, 8))

        tk.Label(card, text="TOPOLOGÍA DETECTADA", font=FONT_SECTION,
                 fg=FG_BLUE, bg=BG_PANEL).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Frame(card, bg=ACCENT, height=1).pack(fill="x", padx=14, pady=(0, 6))

        self._canvas = TopologyCanvas(card, bg=BG_DARK)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_details_panel(self, parent):
        card = tk.Frame(parent, bg=BG_PANEL)
        card.pack(fill="x")

        tk.Label(card, text="DETALLES DEL PUERTO", font=FONT_SECTION,
                 fg=FG_BLUE, bg=BG_PANEL).pack(anchor="w", padx=14, pady=(10, 4))
        tk.Frame(card, bg=ACCENT, height=1).pack(fill="x", padx=14, pady=(0, 8))

        # Grid de tarjetas de detalle
        grid = tk.Frame(card, bg=BG_PANEL)
        grid.pack(fill="x", padx=14, pady=(0, 14))

        col_a = tk.Frame(grid, bg=BG_CARD)
        col_a.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)
        col_b = tk.Frame(grid, bg=BG_CARD)
        col_b.pack(side="left", fill="both", expand=True, pady=4)

        # Columna A
        for row in col_a, col_b:
            tk.Frame(row, bg=BG_CARD, height=6).pack()

        self._row_protocol = self._detail_card(col_a, "Protocolo")
        self._row_switch   = self._detail_card(col_a, "Switch")
        self._row_ip       = self._detail_card(col_a, "IP del Switch")
        self._row_model    = self._detail_card(col_a, "Modelo")

        self._row_port     = self._detail_card(col_b, "Puerto en Switch")
        self._row_desc     = self._detail_card(col_b, "Descripción")
        self._row_vlan_id  = self._detail_card(col_b, "VLAN ID")
        self._row_vlan_nm  = self._detail_card(col_b, "VLAN Nombre")

        for row in col_a, col_b:
            tk.Frame(row, bg=BG_CARD, height=6).pack()

    def _detail_card(self, parent, label: str) -> DetailRow:
        row = DetailRow(parent, label)
        row.pack(fill="x", padx=10, pady=2)
        return row

    # ─── Lógica de escaneo ────────────────────────────────────────────────────

    def _on_scan(self):
        iface = self._iface_var.get()
        if not iface:
            messagebox.showerror("Error", "Seleccioná una interfaz de red.")
            return

        try:
            timeout = int(self._timeout_var.get())
            if timeout < 10:
                timeout = 10
        except ValueError:
            timeout = 90

        self._scanning = True
        self._btn_scan.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._status_led.config(text="●  Escaneando...", fg=FG_YELLOW)
        self._canvas.set_scanning()
        self._clear_details()

        friendly = getattr(self, "_iface_name_map", {}).get(iface, iface)
        self._log("── Inicio de escaneo ──────────────────", "info")
        self._log(f"Interfaz : {friendly}", "info")
        self._log(f"Timeout  : {timeout}s", "info")

        self._stop_event = start_listen(
            iface=iface,
            timeout=timeout,
            on_found=lambda p: self._msg_queue.put(("found", p)),
            on_log=lambda m: self._msg_queue.put(("log", m)),
        )

    def _on_stop(self):
        if self._stop_event:
            self._stop_event.set()
        self._end_scan(timeout=False)

    def _on_clear(self):
        self._on_stop()
        self._clear_details()
        self._clear_log()
        self._canvas.set_idle()
        self._current_port = None

    def _end_scan(self, timeout=False):
        self._scanning = False
        self._btn_scan.config(state="normal")
        self._btn_stop.config(state="disabled")
        if timeout:
            self._status_led.config(text="●  Timeout", fg=FG_RED)
            self._canvas.set_timeout()
        else:
            if not self._current_port:
                self._status_led.config(text="●  Detenido", fg=FG_MUTED)

    def _on_found(self, port: DiscoveredPort):
        """Llamado cuando se detecta un switch."""
        self._current_port = port
        self._scanning = False
        self._btn_scan.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._status_led.config(text=f"●  Detectado via {port.protocol}", fg=FG_GREEN)
        self._canvas.set_found(port)
        self._update_details(port)

        self._log(f"Switch detectado: {port.display_switch()}", "success")
        self._log(f"Puerto : {port.display_port()}", "success")
        self._log(f"VLAN   : {port.display_vlan()}", "success")

        # Enriquecer con SNMP si hay IP
        community = self._snmp_var.get() or "public"
        if port.switch_ip:
            self._log("Consultando SNMP para información adicional...", "info")
            start_snmp_enrich(
                port=port,
                community=community,
                on_log=lambda m: self._msg_queue.put(("log", m)),
                on_done=lambda p: self._msg_queue.put(("snmp_done", p)),
            )

    # ─── Cola de mensajes (thread-safe GUI) ───────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self._msg_queue.get_nowait()
                if msg_type == "found":
                    self._on_found(payload)
                elif msg_type == "log":
                    # Detectar si es timeout
                    if "Timeout" in payload or "timeout" in payload:
                        self._log(payload, "warning")
                        if self._scanning:
                            self._end_scan(timeout=True)
                    elif "Error" in payload or "error" in payload:
                        self._log(payload, "error")
                    else:
                        self._log(payload, "info")
                elif msg_type == "snmp_done":
                    self._update_details(payload)
                    self._canvas.set_found(payload)
                    self._log("Enriquecimiento SNMP completo.", "success")
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    # ─── Actualización de detalles ────────────────────────────────────────────

    def _update_details(self, port: DiscoveredPort):
        proto_color = FG_BLUE if port.protocol == "LLDP" else FG_YELLOW
        self._row_protocol.set(port.protocol, proto_color)
        self._row_switch.set(port.display_switch(), FG_TEXT)
        self._row_ip.set(port.switch_ip or "—", FG_GREEN if port.switch_ip else FG_MUTED)
        self._row_model.set(port.switch_model[:60] if port.switch_model else "—", FG_MUTED)
        self._row_port.set(port.display_port(), FG_GREEN)
        self._row_desc.set(port.display_description(), FG_TEXT)

        if port.vlan_id:
            vc = vlan_color(port.vlan_id)
            self._row_vlan_id.set(str(port.vlan_id), vc)
        else:
            self._row_vlan_id.set("—")

        self._row_vlan_nm.set(port.vlan_name or "—",
                               FG_PURPLE if port.vlan_name else FG_MUTED)

    def _clear_details(self):
        for row in (self._row_protocol, self._row_switch, self._row_ip,
                    self._row_model, self._row_port, self._row_desc,
                    self._row_vlan_id, self._row_vlan_nm):
            row.set("—")

    # ─── Log ─────────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log_text.config(state="normal")
        self._log_text.insert("end", f"[{ts}] ", "ts")
        self._log_text.insert("end", f"{msg}\n", level)
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    # ─── Utilidades ───────────────────────────────────────────────────────────

    def _populate_interfaces(self):
        ifaces = list_physical_interfaces()
        # Etiqueta para el combo: "Ethernet  (192.168.1.10)"
        labels = [f"{i['name']}  ({i['ip']})" for i in ifaces]
        # Valor que se pasa a Scapy: el GUID Npcap en Windows, nombre en Linux
        guids  = [i["guid"] for i in ifaces]
        # Nombre amigable para el log
        names  = [i["name"] for i in ifaces]

        self._iface_combo["values"] = labels
        if labels:
            self._iface_combo.current(0)
            # label → guid  (lo que Scapy entiende)
            self._iface_map = dict(zip(labels, guids))
            # guid  → nombre legible (para el log)
            self._iface_name_map = dict(zip(guids, names))
            self._iface_combo.bind(
                "<<ComboboxSelected>>",
                lambda _: self._iface_var.set(
                    self._iface_map.get(self._iface_combo.get(),
                                        self._iface_combo.get())
                )
            )
            # Primer valor: GUID de la primera interfaz
            self._iface_var.set(guids[0])

    def _center_window(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - 1200) // 2
        y  = (sh - 750)  // 2
        self.geometry(f"1200x750+{x}+{y}")
