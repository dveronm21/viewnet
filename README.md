<div align="center">

# 🌐 ViewNet

### Mapeador de red empresarial para identificar VLAN, switch y puerto desde una toma de red

**LLDP · CDP · SNMP · Diagnóstico de red · Infraestructura**

</div>

---

## ¿Qué hace ViewNet?

ViewNet es una herramienta para técnicos y administradores de red que necesitan saber rápidamente **a qué switch, puerto y VLAN está conectada una boca de red**.

La idea es simplificar una tarea cotidiana de infraestructura: conectar una notebook a una toma RJ45 y obtener información útil sin tener que recorrer manualmente toda la red.

## Funciones principales

- Detecta información mediante LLDP y CDP.
- Identifica el switch conectado.
- Muestra la dirección IP del switch cuando está disponible.
- Informa el puerto físico detectado.
- Identifica la VLAN asociada.
- Puede complementar la información mediante SNMP.
- Incluye interfaz gráfica y modo por terminal.

## Ejecución

### Interfaz gráfica

```powershell
python main.py
```

### Modo terminal

```powershell
python main.py --cli
```

## Estructura del proyecto

```text
viewnet/
├── core/              Lógica de descubrimiento de red
├── models/            Modelos de datos
├── ui/                Interfaz gráfica
├── main.py            Punto de entrada
├── install.bat        Instalación en Windows
├── run.bat            Ejecución rápida
└── requirements.txt   Dependencias de Python
```

## ¿Para qué puede servir?

- Relevamientos de cableado y puestos de trabajo.
- Diagnóstico de conexiones de red.
- Identificación rápida de puertos de switch.
- Verificación de VLAN asignadas.
- Soporte técnico en sitio.
- Documentación de infraestructura.

## Enfoque

ViewNet busca resolver una necesidad concreta de campo con una herramienta simple y directa. En vez de depender de planillas o de ingresar manualmente a distintos switches, intenta obtener la información disponible desde el propio punto de conexión.

## Uso responsable

Utilizar únicamente en redes propias o administradas con autorización. Las consultas SNMP, LLDP y CDP deben realizarse respetando las políticas de seguridad de cada organización.

---

<div align="center">

**Desarrollado por [Douglas Verón](https://github.com/dveronm21)**

*Infraestructura · Redes · Ciberseguridad · Automatización · Ingeniería de software*

</div>
