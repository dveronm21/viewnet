from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class DiscoveredPort:
    protocol: str = ""
    switch_name: str = ""
    switch_ip: str = ""
    local_port: str = ""
    port_description: str = ""
    vlan_id: Optional[int] = None
    vlan_name: str = ""
    chassis_id: str = ""
    switch_model: str = ""
    port_alias: str = ""
    detected_at: float = field(default_factory=time.time)

    def display_switch(self) -> str:
        return self.switch_name or self.switch_ip or "Desconocido"

    def display_port(self) -> str:
        return self.local_port or "Desconocido"

    def display_vlan(self) -> str:
        if self.vlan_name:
            return f"{self.vlan_id} — {self.vlan_name}"
        if self.vlan_id:
            return str(self.vlan_id)
        return "No detectada"

    def display_description(self) -> str:
        return self.port_alias or self.port_description or "Sin descripción"
