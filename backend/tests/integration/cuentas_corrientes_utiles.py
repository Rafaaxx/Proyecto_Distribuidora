"""Utilidades compartidas de las pruebas de integración de `cuentas_corrientes`.

Crea lo que toda prueba del libro necesita para no insertar en el vacío: una
organización (con su configuración, que el servicio lee para reconocer al
consumidor final), un usuario con sus permisos, un dispositivo (`dispositivo_id`
es `NOT NULL` con FK compuesta, `design.md` D14), clientes y proveedores.

Es un módulo y no un `conftest.py` para que las pruebas lo importen de forma
explícita (`from cuentas_corrientes_utiles import ...`, mismo mecanismo que
`from conftest import ...`, porque `tests/integration` no es un paquete).
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.ids import nuevo_id
from app.modules.clientes import repository as clientes_repository
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import ConfiguracionOrganizacion, Organizacion
from app.modules.proveedores import repository as proveedores_repository

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)


# Prefijo de dispositivo de dos caracteres hexadecimales, UNICO por proceso (hasta 256): con
# `uuid4().hex[:2]` dos dispositivos de una misma organizacion chocaban en
# `ux_dispositivo__org_prefijo` una de cada 256 veces (falla intermitente).
_PREFIJOS = itertools.cycle(range(256))


def crear_organizacion(sesion: Session, *, con_configuracion: bool = True) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba cuentas corrientes",
        slug=f"org-cc-{uuid4().hex[:8]}",
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    if con_configuracion:
        agregar_configuracion(sesion, organizacion.id)
    return organizacion


def agregar_configuracion(sesion: Session, organizacion_id: UUID) -> None:
    """La fila de configuración de una organización creada a mano (responsable inscripto,
    modo B con modalidad `CLIENTE`): `COSTO_INFORMAR` y `COMPRA_CONFIRMAR` leen de ella la
    regla de crédito fiscal (change 11b)."""
    sesion.add(
        ConfiguracionOrganizacion(
            organizacion_id=organizacion_id,
            condicion_iva="RESPONSABLE_INSCRIPTO",
            modo_impositivo="B",
            lista_precio_default_id=None,
            politica_credito_default="ADVERTIR",
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            descuento_manual_habilitado=False,
            motivo_obligatorio_descuento=None,
            motivo_obligatorio_lista=True,
            redondeo_multiplo=None,
            redondeo_direccion=None,
            permite_consumidor_final=None,
            cliente_consumidor_final_id=None,
            estado_facturacion_default="PENDIENTE",
            modalidad_iva_default="CLIENTE",
            intentos_pin_max=3,
            desvio_reloj_max_segundos=None,
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
            actualizado_por_id=None,
        )
    )
    sesion.flush()


def crear_usuario_y_dispositivo(
    sesion: Session,
    organizacion_id: UUID,
    *,
    permisos: frozenset[str] = frozenset({"IMPORTAR_DATOS"}),
) -> tuple[UUID, UUID]:
    """Devuelve `(usuario_id, dispositivo_id)` de la organización."""
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre=f"Rol {uuid4().hex[:6]}",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in sorted(permisos):
        identidad_repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"usuario-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"C{next(_PREFIJOS):02x}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def crear_cliente(
    sesion: Session,
    organizacion_id: UUID,
    *,
    estado: str = "ACTIVO",
    nombre: str = "Kiosco La Esquina",
    es_consumidor_final: bool = False,
) -> UUID:
    cliente = clientes_repository.crear_cliente(
        organizacion_id,
        sesion,
        cliente_id=nuevo_id(),
        nombre=nombre,
        codigo=None,
        razon_social=None,
        documento_tipo=None,
        documento_numero=None,
        direccion="Av. San Martín 1420",
        contacto="Rocío",
        telefono=None,
        email=None,
        lista_precio_id=None,
        estado_facturacion_default=None,
        es_consumidor_final=es_consumidor_final,
        limite_credito=None,
        politica_credito=None,
        tolerancia_offline_tipo=None,
        tolerancia_offline_valor=None,
        estado=estado,
        momento=MOMENTO,
    )
    return cliente.id


def crear_proveedor(
    sesion: Session,
    organizacion_id: UUID,
    *,
    activo: bool = True,
    nombre: str | None = None,
) -> UUID:
    proveedor = proveedores_repository.crear_proveedor(
        organizacion_id,
        sesion,
        proveedor_id=nuevo_id(),
        nombre=nombre or f"Bodega Norte {uuid4().hex[:6]}",
        cuit=None,
        contacto=None,
        telefono=None,
        email=None,
        activo=activo,
        momento=MOMENTO,
    )
    return proveedor.id


def insertar_movimiento_sql(sesion: Session, **cambios: object) -> UUID:
    """`INSERT` directo en `cuenta_movimiento` para probar la base sin pasar
    por el servicio. Los valores por defecto arman un movimiento
    `SALDO_INICIAL AUMENTA` de un cliente; `organizacion_id`, `entidad_id`,
    `usuario_id` y `dispositivo_id` los pasa quien llama."""
    movimiento_id = uuid4()
    valores: dict[str, object] = {
        "id": movimiento_id,
        "cuenta_tipo": "CLIENTE",
        "tipo": "SALDO_INICIAL",
        "sentido": "AUMENTA",
        "importe": Decimal("150000.00"),
        "origen_tipo": "SALDO_INICIAL",
        "origen_id": uuid4(),
        "occurred_at": MOMENTO,
        "registered_at": MOMENTO,
        "operation_id": uuid4(),
        **cambios,
    }
    columnas = ", ".join(valores)
    marcadores = ", ".join(f":{columna}" for columna in valores)
    sesion.execute(
        text(f"INSERT INTO cuenta_movimiento ({columnas}) VALUES ({marcadores})"), valores
    )
    return movimiento_id
