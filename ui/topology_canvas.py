"""
Canvas de topología de red.
Dibuja el dispositivo local, el cable y el switch detectado.
"""
import tkinter as tk
import math
import time


# Paleta de colores
CLR_BG       = "#0f1117"
CLR_PC       = "#2563eb"
CLR_SWITCH   = "#059669"
CLR_CABLE    = "#6b7280"
CLR_ACTIVE   = "#10b981"
CLR_TEXT     = "#f1f5f9"
CLR_SUBTEXT  = "#94a3b8"
CLR_VLAN_BG  = "#7c3aed"
CLR_BORDER   = "#1e293b"
CLR_SCANNING = "#f59e0b"

VLAN_COLORS = [
    "#7c3aed", "#0891b2", "#059669", "#d97706",
    "#dc2626", "#db2777", "#2563eb", "#65a30d",
]


def vlan_color(vlan_id) -> str:
    if not vlan_id:
        return "#4b5563"
    try:
        return VLAN_COLORS[int(vlan_id) % len(VLAN_COLORS)]
    except Exception:
        return "#4b5563"


class TopologyCanvas(tk.Canvas):
    """
    Widget Canvas que dibuja la topología de red detectada.
    Soporta estado: idle / scanning / found / timeout
    """

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", CLR_BG)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)

        self._state = "idle"     # idle | scanning | found | timeout
        self._port  = None       # DiscoveredPort
        self._anim_angle = 0.0
        self._anim_id    = None
        self._pulse      = 0.0
        self._pulse_dir  = 1

        self.bind("<Configure>", lambda _: self._redraw())
        self._redraw()

    # ─── API pública ───────────────────────────────────────────

    def set_idle(self):
        self._state = "idle"
        self._port  = None
        self._stop_anim()
        self._redraw()

    def set_scanning(self):
        self._state = "scanning"
        self._port  = None
        self._start_anim()

    def set_found(self, port):
        self._state = "found"
        self._port  = port
        self._stop_anim()
        self._redraw()

    def set_timeout(self):
        self._state = "timeout"
        self._stop_anim()
        self._redraw()

    # ─── Animación ─────────────────────────────────────────────

    def _start_anim(self):
        self._stop_anim()
        self._tick()

    def _stop_anim(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _tick(self):
        self._anim_angle = (self._anim_angle + 6) % 360
        self._pulse      += 0.05 * self._pulse_dir
        if self._pulse >= 1.0 or self._pulse <= 0.0:
            self._pulse_dir *= -1
        self._redraw()
        self._anim_id = self.after(40, self._tick)

    # ─── Dibujo ────────────────────────────────────────────────

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        # Fondo con gradiente simulado (rectángulos)
        steps = 20
        for i in range(steps):
            r = int(15 + i * 0.5)
            g = int(17 + i * 0.3)
            b = int(23 + i * 0.8)
            color = f"#{r:02x}{g:02x}{b:02x}"
            y0 = int(h * i / steps)
            y1 = int(h * (i + 1) / steps)
            self.create_rectangle(0, y0, w, y1, fill=color, outline="")

        if self._state == "idle":
            self._draw_idle(w, h)
        elif self._state == "scanning":
            self._draw_scanning(w, h)
        elif self._state == "found":
            self._draw_found(w, h)
        elif self._state == "timeout":
            self._draw_timeout(w, h)

    def _draw_idle(self, w, h):
        cx, cy = w // 2, h // 2
        self.create_text(cx, cy - 12, text="⬡",
                         font=("Segoe UI", 40), fill="#1e293b")
        self.create_text(cx, cy + 30,
                         text="Seleccioná una interfaz y presioná Escanear",
                         font=("Segoe UI", 11), fill=CLR_SUBTEXT)

    def _draw_scanning(self, w, h):
        cx, cy = w // 2, h // 2

        # Ícono de PC (izquierda)
        px = int(w * 0.18)
        self._draw_pc(px, cy, label="Mi equipo")

        # Anillo giratorio (centro)
        r  = 30
        a  = math.radians(self._anim_angle)
        # Arco de progreso
        for i in range(12):
            ang = math.radians(self._anim_angle + i * 30)
            alpha = int(255 * (i / 12))
            color = self._blend(CLR_SCANNING, CLR_BG, 1 - i / 12)
            x1 = cx + r * math.cos(ang) - 4
            y1 = cy + r * math.sin(ang) - 4
            self.create_oval(x1, y1, x1+8, y1+8, fill=color, outline="")

        # Texto de estado pulsante
        pulse_alpha = int(180 + 75 * self._pulse)
        color = self._fade(CLR_SCANNING, pulse_alpha)
        self.create_text(cx, cy + 55,
                         text="Buscando switch...",
                         font=("Segoe UI", 12, "bold"), fill=CLR_SCANNING)
        self.create_text(cx, cy + 78,
                         text="Esperando LLDP / CDP",
                         font=("Segoe UI", 10), fill=CLR_SUBTEXT)

        # Línea de cable animada
        dots = 7
        spacing = (cx - px - 40) / dots
        for i in range(dots):
            x = px + 30 + i * spacing
            phase = (i / dots + self._anim_angle / 360) % 1.0
            size  = 2 + 3 * abs(math.sin(phase * math.pi))
            clr   = self._blend(CLR_SCANNING, CLR_CABLE, phase)
            self.create_oval(x - size, cy - size, x + size, cy + size,
                             fill=clr, outline="")

        # Signo de interrogación (switch desconocido)
        sx = int(w * 0.82)
        self._draw_unknown_switch(sx, cy)

    def _draw_found(self, w, h):
        p = self._port
        if not p:
            return

        cy  = h // 2
        px  = int(w * 0.14)
        sx  = int(w * 0.76)
        mid = (px + sx) // 2

        # Ícono de PC
        self._draw_pc(px, cy, label="Mi equipo")

        # Ícono del switch
        self._draw_switch(sx, cy,
                          name=p.display_switch(),
                          ip=p.switch_ip,
                          port=p.display_port(),
                          protocol=p.protocol)

        # Cable con flujo de datos
        self._draw_cable(px + 28, cy, sx - 28, cy)

        # Puerto en el cable
        self.create_oval(mid - 8, cy - 8, mid + 8, cy + 8,
                         fill=CLR_ACTIVE, outline=CLR_BG, width=2)
        self.create_text(mid, cy + 20,
                         text=p.display_port(),
                         font=("Segoe UI", 8), fill=CLR_ACTIVE)

        # Badge de VLAN (arriba)
        if p.vlan_id:
            vc = vlan_color(p.vlan_id)
            vtext = f"VLAN {p.vlan_id}"
            if p.vlan_name:
                vtext += f"  {p.vlan_name}"
            bw = len(vtext) * 7 + 20
            bx = mid
            by = cy - 55
            self.create_rectangle(bx - bw//2, by - 12, bx + bw//2, by + 12,
                                  fill=vc, outline="", width=0)
            self.create_text(bx, by, text=vtext,
                             font=("Segoe UI", 9, "bold"), fill="white")

        # Protocolo badge
        self.create_text(mid, h - 18,
                         text=f"Detectado via {p.protocol}  ●  {p.switch_model[:50] if p.switch_model else ''}",
                         font=("Segoe UI", 8), fill=CLR_SUBTEXT)

    def _draw_timeout(self, w, h):
        cx, cy = w // 2, h // 2
        self.create_text(cx, cy - 15, text="✕",
                         font=("Segoe UI", 36), fill="#ef4444")
        self.create_text(cx, cy + 20,
                         text="Sin respuesta LLDP/CDP",
                         font=("Segoe UI", 12, "bold"), fill="#ef4444")
        self.create_text(cx, cy + 42,
                         text="Verificá que LLDP esté habilitado en el switch",
                         font=("Segoe UI", 10), fill=CLR_SUBTEXT)

    # ─── Elementos gráficos ────────────────────────────────────

    def _draw_pc(self, cx, cy, label=""):
        # Monitor
        self.create_rectangle(cx - 22, cy - 18, cx + 22, cy + 10,
                               fill="#1e40af", outline=CLR_PC, width=2)
        # Pantalla
        self.create_rectangle(cx - 17, cy - 14, cx + 17, cy + 7,
                               fill="#172554", outline="")
        # Letra en pantalla
        self.create_text(cx, cy - 4, text=">_",
                         font=("Courier", 8, "bold"), fill=CLR_ACTIVE)
        # Base
        self.create_rectangle(cx - 6, cy + 10, cx + 6, cy + 16,
                               fill=CLR_PC, outline="")
        self.create_rectangle(cx - 14, cy + 16, cx + 14, cy + 19,
                               fill=CLR_PC, outline="")
        # RJ45 plug
        self.create_rectangle(cx + 22, cy - 4, cx + 28, cy + 4,
                               fill="#d97706", outline="#f59e0b", width=1)
        if label:
            self.create_text(cx, cy + 30,
                             text=label, font=("Segoe UI", 9, "bold"),
                             fill=CLR_TEXT)

    def _draw_switch(self, cx, cy, name="", ip="", port="", protocol=""):
        w_box, h_box = 110, 60

        # Sombra
        self.create_rectangle(cx - w_box//2 + 3, cy - h_box//2 + 3,
                               cx + w_box//2 + 3, cy + h_box//2 + 3,
                               fill="#000000", outline="")
        # Cuerpo
        self.create_rectangle(cx - w_box//2, cy - h_box//2,
                               cx + w_box//2, cy + h_box//2,
                               fill="#064e3b", outline=CLR_SWITCH, width=2)
        # Puertos decorativos
        for i in range(8):
            px_port = cx - 44 + i * 12
            self.create_rectangle(px_port, cy - 22, px_port + 8, cy - 14,
                                   fill="#065f46", outline="#10b981", width=1)

        # LED activo en el puerto conectado
        port_idx = min(7, max(0, hash(port) % 8))
        px_active = cx - 44 + port_idx * 12
        self.create_rectangle(px_active, cy - 22, px_active + 8, cy - 14,
                               fill=CLR_ACTIVE, outline=CLR_ACTIVE)

        # Nombre del switch (truncado)
        display_name = name[:18] if len(name) > 18 else name
        self.create_text(cx, cy - 2,
                         text=display_name,
                         font=("Segoe UI", 8, "bold"), fill=CLR_TEXT)
        if ip:
            self.create_text(cx, cy + 12,
                             text=ip, font=("Courier", 8), fill=CLR_SUBTEXT)

        # Badge protocolo
        proto_color = "#2563eb" if protocol == "LLDP" else "#d97706"
        self.create_rectangle(cx - 16, cy - 32, cx + 16, cy - 20,
                               fill=proto_color, outline="")
        self.create_text(cx, cy - 26, text=protocol,
                         font=("Segoe UI", 7, "bold"), fill="white")

        # Puerto conectado (debajo del switch)
        self.create_text(cx, cy + h_box//2 + 14,
                         text=port[:25], font=("Segoe UI", 8), fill=CLR_ACTIVE)

        # RJ45 plug izquierdo
        self.create_rectangle(cx - w_box//2 - 8, cy - 4,
                               cx - w_box//2, cy + 4,
                               fill="#d97706", outline="#f59e0b", width=1)

    def _draw_unknown_switch(self, cx, cy):
        w_box, h_box = 80, 50
        self.create_rectangle(cx - w_box//2, cy - h_box//2,
                               cx + w_box//2, cy + h_box//2,
                               fill="#1e293b", outline="#4b5563", width=2,
                               dash=(4, 4))
        self.create_text(cx, cy - 8, text="?",
                         font=("Segoe UI", 22, "bold"), fill="#4b5563")
        self.create_text(cx, cy + 16, text="Switch",
                         font=("Segoe UI", 8), fill="#4b5563")

    def _draw_cable(self, x1, y1, x2, y2):
        # Cable principal
        self.create_line(x1, y1, x2, y2,
                         fill=CLR_CABLE, width=3, capstyle=tk.ROUND)
        # Flujo de datos (partículas)
        length = math.hypot(x2 - x1, y2 - y1)
        steps  = int(length / 15)
        for i in range(steps):
            t   = i / max(steps, 1)
            x   = x1 + (x2 - x1) * t
            y   = y1 + (y2 - y1) * t
            clr = CLR_ACTIVE if (i % 4 == 0) else CLR_CABLE
            self.create_oval(x - 2, y - 2, x + 2, y + 2,
                             fill=clr, outline="")

    # ─── Utilidades de color ───────────────────────────────────

    @staticmethod
    def _blend(hex1: str, hex2: str, t: float) -> str:
        """Interpola entre dos colores hex, t=0→hex2, t=1→hex1."""
        def parse(h):
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r1, g1, b1 = parse(hex1)
        r2, g2, b2 = parse(hex2)
        r = int(r1 * t + r2 * (1 - t))
        g = int(g1 * t + g2 * (1 - t))
        b = int(b1 * t + b2 * (1 - t))
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _fade(hex_color: str, alpha: int) -> str:
        return hex_color  # tkinter no soporta RGBA, se usa como está
