"""Utilidades compartidas de las pruebas de integración de `importacion` (change 10, grupos
5 y 6): un entorno con organización, usuario con `IMPORTAR_DATOS` y dispositivo, que envía
`IMPORTACION_REGISTRAR` por el bus real (`sync_service.procesar_comando`, mismo criterio que
`test_importacion_comando.py`), más el sembrado de catálogos y maestros por los servicios.

Es un módulo y no un `conftest.py` por el mismo motivo que `cuentas_corrientes_utiles`:
`tests/integration` no es un paquete.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.catalogo.domain.presentaciones import DatosPresentacion
from app.modules.catalogo.models import Categoria, Marca, Presentacion, Producto
from app.modules.clientes import service as clientes_service
from app.modules.configuracion.models import AlicuotaIva
from app.modules.costeo import service as costeo_service
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.cuentas_corrientes.models import CuentaMovimiento
from app.modules.identidad.models import Auditoria
from app.modules.importacion import commands as importacion_commands
from app.modules.importacion.domain.errores import ImportacionConErroresError
from app.modules.importacion.models import Importacion
from app.modules.proveedores.models import CostoInformado
from app.modules.stock import service as stock_service
from app.modules.stock.models import StockMovimiento
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)
TIPO_COMANDO = "IMPORTACION_REGISTRAR"


def errores_de(error: ImportacionConErroresError) -> list[tuple[int, str | None, str]]:
    """`(fila, columna, codigo)` de cada error del informe, en el orden del informe."""
    assert error.extension is not None
    return [(e["fila"], e["columna"], e["codigo"]) for e in error.extension["errores"]]


def contenido(
    tipo: str, filas: list[dict[str, Any]], archivo: str = "planilla.csv"
) -> dict[str, Any]:
    return {"tipo": tipo, "archivo_nombre": archivo, "filas": filas}


def fila_de(numero: int, valores: dict[str, str]) -> dict[str, Any]:
    return {"fila": numero, "valores": valores}


class EntornoDeImportacion:
    def __init__(
        self, sesion: Session, *, permisos: frozenset[str] = frozenset({"IMPORTAR_DATOS"})
    ) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        sesion.commit()

    def fijar_condicion_iva(self, condicion: str) -> None:
        """Pasa la organización a `condicion` por SQL (sin comando ni auditoría), con el modo
        `A` y sin modalidad de IVA que la base exige a una no inscripta (11b, D2)."""
        self.sesion.execute(
            text(
                "UPDATE configuracion_organizacion SET condicion_iva = :c, "
                "modo_impositivo = CASE WHEN :c = 'RESPONSABLE_INSCRIPTO' "
                "THEN modo_impositivo ELSE 'A' END, "
                "modalidad_iva_default = CASE WHEN :c = 'RESPONSABLE_INSCRIPTO' "
                "THEN modalidad_iva_default ELSE NULL END "
                "WHERE organizacion_id = :org"
            ),
            {"c": condicion, "org": self.org},
        )
        self.sesion.commit()

    # --- el comando por el bus ----------------------------------------------------

    def sobre(self, cuerpo: dict[str, Any], *, operation_id: UUID | None = None) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=TIPO_COMANDO,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=cuerpo,
        )

    def enviar(self, cuerpo: dict[str, Any], *, operation_id: UUID | None = None) -> Comando:
        sobre = self.sobre(cuerpo, operation_id=operation_id)
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return importacion_commands.manejar_importacion_registrar(
                sobre,
                validado,  # type: ignore[arg-type]
                sesion=sesion_protegida,
                reloj=RELOJ,
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    # --- sembrado por los servicios ------------------------------------------------

    def categoria(self, nombre: str, *, activa: bool = True, org: UUID | None = None) -> UUID:
        donde = org or self.org
        categoria = catalogo_service.crear_categoria(
            donde, self.sesion, RELOJ, nombre=nombre, actor_id=None
        )
        if not activa:
            catalogo_service.modificar_categoria(
                donde,
                self.sesion,
                RELOJ,
                categoria_id=categoria.id,
                nombre=nombre,
                activo=False,
                actor_id=None,
            )
        self.sesion.commit()
        return categoria.id

    def marca(self, nombre: str, *, activa: bool = True) -> UUID:
        marca = catalogo_service.crear_marca(
            self.org, self.sesion, RELOJ, nombre=nombre, actor_id=None
        )
        if not activa:
            catalogo_service.modificar_marca(
                self.org,
                self.sesion,
                RELOJ,
                marca_id=marca.id,
                nombre=nombre,
                activo=False,
                actor_id=None,
            )
        self.sesion.commit()
        return marca.id

    def alicuota(self, porcentaje: str, *, activa: bool = True, org: UUID | None = None) -> UUID:
        """`porcentaje` como se escribe en la planilla del sistema: `"21"` -> 0.21."""
        alicuota = AlicuotaIva(
            id=nuevo_id(),
            organizacion_id=org or self.org,
            nombre=f"{porcentaje}%",
            valor=Decimal(porcentaje).scaleb(-2),
            activo=activa,
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
        )
        self.sesion.add(alicuota)
        self.sesion.commit()
        return alicuota.id

    def proveedor(self, nombre: str, *, activo: bool = True, org: UUID | None = None) -> UUID:
        proveedor_id = crear_proveedor(self.sesion, org or self.org, nombre=nombre, activo=activo)
        self.sesion.commit()
        return proveedor_id

    def producto(
        self,
        codigo: str,
        presentaciones: list[DatosPresentacion],
        *,
        nombre: str = "Producto",
        categoria_id: UUID,
        proveedor_id: UUID,
        alicuota_id: UUID,
    ) -> UUID:
        """Alta de producto por el servicio de catálogo (como `PRODUCTO_CREAR`)."""
        producto, _ = catalogo_service.crear_producto(
            self.org,
            self.sesion,
            RELOJ,
            codigo=codigo,
            nombre=nombre,
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=proveedor_id,
            unidad_base="unidad",
            alicuota_id=alicuota_id,
            presentaciones=presentaciones,
            actor_id=None,
        )
        self.sesion.commit()
        return producto.id

    def catalogo_base(self) -> None:
        """Lo que casi toda planilla de productos referencia: `Vinos`, `Cervezas`, la
        alícuota 21 y el proveedor `Bodega Sur`."""
        self.categoria("Vinos")
        self.categoria("Cervezas")
        self.alicuota("21")
        self.proveedor("Bodega Sur")

    # --- lecturas ------------------------------------------------------------------

    def productos(self, org: UUID | None = None) -> list[Producto]:
        return list(
            self.sesion.scalars(
                select(Producto)
                .where(Producto.organizacion_id == (org or self.org))
                .order_by(Producto.codigo)
            ).all()
        )

    def presentaciones_de(self, producto_id: UUID) -> list[Presentacion]:
        return list(
            self.sesion.scalars(
                select(Presentacion)
                .where(
                    Presentacion.organizacion_id == self.org,
                    Presentacion.producto_id == producto_id,
                )
                .order_by(Presentacion.nombre)
            ).all()
        )

    def costos(self) -> list[CostoInformado]:
        self.sesion.expire_all()
        return list(
            self.sesion.scalars(
                select(CostoInformado)
                .where(CostoInformado.organizacion_id == self.org)
                .order_by(CostoInformado.vigencia_desde, CostoInformado.costo_base)
            ).all()
        )

    def categorias(self) -> list[Categoria]:
        return list(
            self.sesion.scalars(
                select(Categoria).where(Categoria.organizacion_id == self.org)
            ).all()
        )

    def marcas(self) -> list[Marca]:
        return list(
            self.sesion.scalars(select(Marca).where(Marca.organizacion_id == self.org)).all()
        )

    def importaciones(self) -> list[Importacion]:
        return list(
            self.sesion.scalars(
                select(Importacion).where(Importacion.organizacion_id == self.org)
            ).all()
        )

    def auditorias(self, operation_id: UUID) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(
                    Auditoria.organizacion_id == self.org, Auditoria.operation_id == operation_id
                )
            )
            or 0
        )

    # --- puesta en marcha: ubicaciones, clientes, stock y saldos --------------------

    def ubicacion(
        self,
        nombre: str,
        *,
        tipo: str = "DEPOSITO",
        activa: bool = True,
        org: UUID | None = None,
    ) -> UUID:
        """Alta de ubicación por el servicio de stock (como `UBICACION_CREAR`)."""
        ubicacion = stock_service.crear_ubicacion(
            org or self.org,
            self.sesion,
            RELOJ,
            nombre=nombre,
            tipo=tipo,
            requiere_toma=tipo == "VEHICULO",
            actor_id=None,
        )
        if not activa:
            self.sesion.execute(
                text("UPDATE ubicacion SET activo = false WHERE id = :id"), {"id": ubicacion.id}
            )
        self.sesion.commit()
        return ubicacion.id

    def cliente(
        self,
        codigo: str | None,
        *,
        nombre: str = "Almacén Don Pepe",
        documento: tuple[str, str] | None = None,
        org: UUID | None = None,
    ) -> UUID:
        """Alta de cliente por el servicio (como `CLIENTE_CREAR`)."""
        cliente = clientes_service.crear_cliente(
            org or self.org,
            self.sesion,
            RELOJ,
            nombre=nombre,
            codigo=codigo,
            razon_social=None,
            documento_tipo=None if documento is None else documento[0],
            documento_numero=None if documento is None else documento[1],
            direccion="San Martín 123",
            contacto="Pepe",
            telefono=None,
            email=None,
            estado_facturacion_default=None,
            actor_id=None,
        )
        self.sesion.commit()
        return cliente.id

    def saldo_de_stock(self, producto_id: UUID, ubicacion_id: UUID) -> int:
        self.sesion.expire_all()
        return stock_service.obtener_saldo(
            self.org, self.sesion, producto_id=producto_id, ubicacion_id=ubicacion_id
        )

    def promedio(self, producto_id: UUID) -> Decimal | None:
        self.sesion.expire_all()
        return costeo_service.obtener_promedio(self.org, self.sesion, producto_id)

    def movimientos_de_stock(self, producto_id: UUID | None = None) -> list[StockMovimiento]:
        self.sesion.expire_all()
        consulta = select(StockMovimiento).where(StockMovimiento.organizacion_id == self.org)
        if producto_id is not None:
            consulta = consulta.where(StockMovimiento.producto_id == producto_id)
        return list(
            self.sesion.scalars(
                consulta.order_by(StockMovimiento.registered_at, StockMovimiento.id)
            ).all()
        )

    def saldo_de_cuenta(self, cuenta_tipo: str, entidad_id: UUID) -> Decimal:
        self.sesion.expire_all()
        return cuentas_service.obtener_saldo(
            self.org, self.sesion, cuenta_tipo=cuenta_tipo, entidad_id=entidad_id
        )

    def movimientos_de_cuenta(self, cuenta_tipo: str, entidad_id: UUID) -> list[CuentaMovimiento]:
        self.sesion.expire_all()
        return list(
            self.sesion.scalars(
                select(CuentaMovimiento)
                .where(
                    CuentaMovimiento.organizacion_id == self.org,
                    CuentaMovimiento.cuenta_tipo == cuenta_tipo,
                    CuentaMovimiento.entidad_id == entidad_id,
                )
                .order_by(CuentaMovimiento.registered_at, CuentaMovimiento.id)
            ).all()
        )
