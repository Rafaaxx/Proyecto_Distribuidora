"""Catálogo global de permisos y plantillas de rol (`01` §19, `03` §4,
`03` §17).

Dominio puro: no importa SQLAlchemy ni FastAPI. El catálogo y las plantillas
son datos atados al código (`03` §17): la migración de sincronización
(`identidad: catalogo de permisos`) inserta `PERMISOS_DEL_CATALOGO` con
`ON CONFLICT DO NOTHING`, y la puesta en marcha de una organización
(`python -m app.seed`, tarea 8.13) usa `PLANTILLAS_DE_ROL` para crear sus
cinco roles iniciales. Los roles son plantillas: la organización puede
modificar su composición después (`01` §19).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Permiso:
    codigo: str
    descripcion: str
    modulo: str


# Los 40 permisos de `01` §19 (los 39 originales más `ANULAR_TRANSFERENCIA`, change 14), en el
# mismo orden que la tabla del documento.
PERMISOS_DEL_CATALOGO: tuple[Permiso, ...] = (
    Permiso("ADMIN_USUARIOS", "Usuarios, roles y permisos", "identidad"),
    Permiso("ADMIN_CONFIGURACION", "Configuración de la organización", "identidad"),
    Permiso("GESTIONAR_DISPOSITIVOS", "Ver y revocar dispositivos", "identidad"),
    Permiso("IMPORTAR_DATOS", "Importaciones y puesta en marcha", "importacion"),
    Permiso("GESTIONAR_CATALOGO", "Productos, presentaciones, categorías", "catalogo"),
    Permiso("GESTIONAR_CLIENTES", "Alta y edición de clientes", "clientes"),
    Permiso("GESTIONAR_CREDITO", "Límite, política y tolerancia de clientes", "clientes"),
    Permiso("GESTIONAR_PROVEEDORES", "Alta y edición de proveedores", "proveedores"),
    Permiso("VER_COSTOS", "Ver costos", "costeo"),
    Permiso("EDITAR_COSTOS", "Registrar costos informados", "proveedores"),
    Permiso("VER_UTILIDAD", "Ver utilidad", "costeo"),
    Permiso("GESTIONAR_LISTAS", "Reglas de margen, redondeo y borradores", "precios"),
    Permiso("PUBLICAR_LISTAS", "Publicar y anular versiones", "precios"),
    Permiso("USAR_LISTA_ANTERIOR", "Lista no asignada o versión anterior en venta", "precios"),
    Permiso("GESTIONAR_DESCUENTOS", "Reglas de descuento", "descuentos"),
    Permiso("REGISTRAR_COMPRA", "Registrar compras", "proveedores"),
    Permiso("ANULAR_COMPRA", "Anular compras", "proveedores"),
    Permiso("REGISTRAR_PAGO_PROVEEDOR", "Registrar pagos", "proveedores"),
    Permiso("ANULAR_PAGO_PROVEEDOR", "Anular pagos", "proveedores"),
    Permiso("TRANSFERIR_STOCK", "Transferencias", "stock"),
    Permiso("ANULAR_TRANSFERENCIA", "Anular transferencias de otros usuarios", "stock"),
    Permiso("AJUSTAR_STOCK", "Ajustes", "stock"),
    Permiso("PERMITIR_STOCK_NEGATIVO", "Operar con stock negativo online", "stock"),
    Permiso("ABRIR_JORNADA", "Abrir jornada y tomar ubicación", "stock"),
    Permiso("RENDIR_JORNADA", "Rendir y cerrar jornada", "stock"),
    Permiso("LIBERAR_UBICACION", "Liberación forzada", "stock"),
    Permiso("VENDER", "Confirmar ventas", "ventas"),
    Permiso("ANULAR_VENTA", "Anular ventas", "ventas"),
    Permiso("DESCUENTO_MANUAL", "Descuento manual hasta el tope del rol", "ventas"),
    Permiso("AUTORIZAR_DESCUENTO", "Superar tope de descuento", "ventas"),
    Permiso("SUPERAR_CREDITO", "Vender con exceso de crédito", "ventas"),
    Permiso("VENDER_CLIENTE_SUSPENDIDO", "Vender a suspendidos", "ventas"),
    Permiso("REGISTRAR_COBRANZA", "Registrar cobranzas", "cobranzas"),
    Permiso("ANULAR_COBRANZA", "Anular cobranzas", "cobranzas"),
    Permiso("REVISAR_OBSERVACIONES", "Resolver observaciones", "sync"),
    Permiso("VER_REPORTES", "Reportes", "reportes"),
    Permiso("VER_AUDITORIA", "Consultar auditoría", "auditoria"),
    Permiso("FACTURAR", "Emitir facturas", "facturacion"),
    Permiso("FACTURAR_ABSORBIENDO_IVA", "Emitir con IVA absorbido", "facturacion"),
    Permiso("ANULAR_FACTURA", "Anular facturas", "facturacion"),
)

# Nombres canónicos de las cinco plantillas de rol (`01` §19).
ADMINISTRADOR = "Administrador"
ADMINISTRACION = "Administración"
SUPERVISOR_COMERCIAL = "Supervisor comercial"
VENDEDOR_REPARTIDOR = "Vendedor/Repartidor"
CONSULTA_DIRECCION = "Consulta/Dirección"

# Composición de cada plantilla: el subconjunto de códigos de
# `PERMISOS_DEL_CATALOGO` que le confiere `01` §19. El Administrador tiene
# los 40 (todas las columnas de la tabla marcan ADM).
_TODOS_LOS_CODIGOS = frozenset(permiso.codigo for permiso in PERMISOS_DEL_CATALOGO)

PLANTILLAS_DE_ROL: dict[str, frozenset[str]] = {
    ADMINISTRADOR: frozenset(_TODOS_LOS_CODIGOS),
    ADMINISTRACION: frozenset(
        {
            "GESTIONAR_CATALOGO",
            "GESTIONAR_CLIENTES",
            "GESTIONAR_CREDITO",
            "GESTIONAR_PROVEEDORES",
            "VER_COSTOS",
            "EDITAR_COSTOS",
            "VER_UTILIDAD",
            "GESTIONAR_LISTAS",
            "REGISTRAR_COMPRA",
            "ANULAR_COMPRA",
            "REGISTRAR_PAGO_PROVEEDOR",
            "ANULAR_PAGO_PROVEEDOR",
            "TRANSFERIR_STOCK",
            # Change 14, D5 punto 5: unico lugar que decide que plantillas (ademas del
            # Administrador, que tiene todos) reciben `ANULAR_TRANSFERENCIA`; la
            # migracion `f3a4b5c6d7e8` y la siembra lo derivan de aca.
            "ANULAR_TRANSFERENCIA",
            "AJUSTAR_STOCK",
            "RENDIR_JORNADA",
            "ANULAR_VENTA",
            "REGISTRAR_COBRANZA",
            "ANULAR_COBRANZA",
            "REVISAR_OBSERVACIONES",
            "VER_REPORTES",
            "FACTURAR",
            "ANULAR_FACTURA",
        }
    ),
    SUPERVISOR_COMERCIAL: frozenset(
        {
            "GESTIONAR_DISPOSITIVOS",
            "GESTIONAR_CLIENTES",
            "USAR_LISTA_ANTERIOR",
            "TRANSFERIR_STOCK",
            "ABRIR_JORNADA",
            "RENDIR_JORNADA",
            "LIBERAR_UBICACION",
            "VENDER",
            "ANULAR_VENTA",
            "DESCUENTO_MANUAL",
            "AUTORIZAR_DESCUENTO",
            "SUPERAR_CREDITO",
            "VENDER_CLIENTE_SUSPENDIDO",
            "REGISTRAR_COBRANZA",
            "ANULAR_COBRANZA",
            "REVISAR_OBSERVACIONES",
            "VER_REPORTES",
        }
    ),
    VENDEDOR_REPARTIDOR: frozenset(
        {
            "TRANSFERIR_STOCK",
            "ABRIR_JORNADA",
            "VENDER",
            "DESCUENTO_MANUAL",
            "REGISTRAR_COBRANZA",
        }
    ),
    CONSULTA_DIRECCION: frozenset({"VER_UTILIDAD", "VER_REPORTES", "VER_AUDITORIA"}),
}

# Tope de descuento por defecto de cada plantilla (`01` §19: "Administrador
# (sin tope)" -> `1.000000`; el resto arranca en `0` salvo Supervisor y
# Vendedor, que son quienes ejercen `DESCUENTO_MANUAL` -- el tope concreto es
# un valor de configuración de la organización, no fijado por `01`, así que
# la puesta en marcha (tarea 8.13) lo recibe como parámetro y no hay un valor
# "correcto" único que esta capa de dominio pueda imponer; se deja fuera de
# `PLANTILLAS_DE_ROL` a propósito.
