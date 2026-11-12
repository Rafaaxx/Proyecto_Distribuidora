"""Entorno compartido de las pruebas de `VENTA_CONFIRMAR` (change 18a, grupo 7).

Una organización monotributista (modo `A`, modalidad nula) con su usuario y dispositivo (con los
permisos que se pidan), `Kiosco La Esquina` con saldo de `150000.00`, "Depósito central", Vino A
(21 %; "Caja x6" de referencia y "Botella" de una unidad) con 48 botellas a $1.050, la lista
"General" (predeterminada) con la versión 1 vigente y Vino A a $12.500 la caja, los medios
"Efectivo" y "Transferencia" y el motivo de `LISTA_ANTERIOR`.

Los comandos se procesan por `sync_service.procesar_comando`, que maneja la transacción (mismo
criterio que `cobranzas_utiles.py`, del que hereda). Es un módulo y no un `conftest.py` porque
`tests/integration` no es un paquete.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from cobranzas_utiles import Entorno as EntornoDeCobranzas
from cuentas_corrientes_utiles import crear_organizacion
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import (
    crear_presentacion_referencia_sql,
    crear_presentacion_sql,
    crear_producto_sql,
    crear_ubicacion_sql,
)
from ventas_utiles import insertar_sql, sembrar_lista_sql

from app.commands import registro
from app.commands.credenciales import CredencialDePin
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.costeo.models import CostoProducto
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.models import Dispositivo
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeMovimiento
from app.modules.stock.models import StockMovimiento
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.ventas import commands as ventas_commands  # noqa: F401 (registra el handler)
from app.modules.ventas.models import Venta, VentaLinea, VentaLineaDescuento

MOMENTO_VENTA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
RELOJ_VENTA = FixedClock(MOMENTO_VENTA)
VENTA_CONFIRMAR = "VENTA_CONFIRMAR"
PERMISOS_DE_VENTA = frozenset({"VENDER"})
PERMISOS_DE_SUPERVISOR = frozenset(
    {"VENDER", "USAR_LISTA_ANTERIOR", "PERMITIR_STOCK_NEGATIVO", "VENDER_CLIENTE_SUSPENDIDO"}
)
PRECIO_VINO = "12500.00"


class EntornoVenta(EntornoDeCobranzas):
    """Ver el docstring del módulo."""

    def __init__(
        self,
        sesion: Session,
        *,
        permisos: frozenset[str] = PERMISOS_DE_VENTA,
        saldo_inicial: str | None = "150000.00",
        stock_inicial: int = 48,
        costo_inicial: str | None = "1050",
        condicion_iva: str = "MONOTRIBUTO",
        modo_impositivo: str = "A",
    ) -> None:
        super().__init__(sesion, permisos=permisos, saldo_inicial=saldo_inicial)
        self._correlativo = 0
        self.deposito_id = crear_ubicacion_sql(sesion, self.org, nombre="Depósito central")
        self.vino_id = crear_producto_sql(sesion, self.org, nombre="Vino A")
        self.caja_id = crear_presentacion_referencia_sql(
            sesion, self.org, self.vino_id, unidades_base=6
        )
        self.botella_id = crear_presentacion_sql(
            sesion, self.org, self.vino_id, nombre="Botella", unidades_base=1
        )
        lista = sembrar_lista_sql(sesion, self.org, self.usuario_id)
        self.lista_id, self.version_id = lista.lista_id, lista.version_id
        self.poner_precio(self.version_id, self.vino_id, PRECIO_VINO, 6)
        self.motivo_lista_id = self.crear_motivo("LISTA_ANTERIOR", "Precio acordado con el cliente")
        self.configurar(
            condicion_iva=condicion_iva,
            modo_impositivo=modo_impositivo,
            lista_precio_default_id=self.lista_id,
        )
        if stock_inicial and costo_inicial is not None:
            self.comprar(self.vino_id, stock_inicial, costo_inicial)
        sesion.commit()
        self.prefijo = str(
            sesion.scalar(
                select(Dispositivo.prefijo).where(
                    Dispositivo.organizacion_id == self.org, Dispositivo.id == self.dispositivo_id
                )
            )
        )

    # --- armado de datos ------------------------------------------------------------

    def configurar(self, **columnas: object) -> None:
        """`UPDATE` de `configuracion_organizacion` (condición, modo, lista, motivo, desvío)."""
        valores: dict[str, object] = dict(columnas)
        if valores.get("condicion_iva") == "MONOTRIBUTO":
            valores.setdefault("modalidad_iva_default", None)
        asignaciones = ", ".join(f"{columna} = :{columna}" for columna in valores)
        self.sesion.execute(
            text(
                f"UPDATE configuracion_organizacion SET {asignaciones} "
                "WHERE organizacion_id = :organizacion_id"
            ),
            {**valores, "organizacion_id": self.org},
        )

    def actualizar_cliente(self, cliente_id: UUID, **columnas: object) -> None:
        """`UPDATE` de columnas del cliente (estado, lista, estado de facturación)."""
        asignaciones = ", ".join(f"{columna} = :{columna}" for columna in columnas)
        self.sesion.execute(
            text(f"UPDATE cliente SET {asignaciones} WHERE organizacion_id = :o AND id = :c"),
            {**columnas, "o": self.org, "c": cliente_id},
        )

    def poner_precio(
        self, version_id: UUID, producto_id: UUID, precio: str, unidades_referencia: int
    ) -> None:
        insertar_sql(
            self.sesion,
            "precio_item",
            {
                "id": uuid4(),
                "organizacion_id": self.org,
                "version_id": version_id,
                "producto_id": producto_id,
                "unidades_referencia": unidades_referencia,
                "precio_final": precio,
                "manual": True,
            },
        )

    def crear_version(
        self,
        lista_id: UUID,
        numero: int,
        desde: datetime,
        *,
        estado: str = "PUBLICADA",
        precio_vino: str | None = None,
    ) -> UUID:
        """Una versión de la lista (publicada salvo que se pida otro estado) con el precio de
        Vino A si se indica."""
        version_id = uuid4()
        valores: dict[str, object] = {
            "id": version_id,
            "organizacion_id": self.org,
            "lista_id": lista_id,
            "numero": numero,
            "estado": estado,
            "creado_por_id": self.usuario_id,
            "creado_en": desde,
            "operation_id": uuid4(),
        }
        if estado in {"PUBLICADA", "ANULADA"}:
            valores.update(
                vigencia_desde=desde, publicado_por_id=self.usuario_id, publicado_en=desde
            )
        if estado == "ANULADA":
            valores.update(anulado_por_id=self.usuario_id, anulado_en=desde)
        insertar_sql(self.sesion, "lista_version", valores)
        if precio_vino is not None:
            self.poner_precio(version_id, self.vino_id, precio_vino, 6)
        return version_id

    def crear_lista(self, nombre: str, *, activo: bool = True) -> UUID:
        lista_id = uuid4()
        insertar_sql(
            self.sesion,
            "lista_precio",
            {
                "id": lista_id,
                "organizacion_id": self.org,
                "nombre": nombre,
                "redondeo_multiplo": 100,
                "redondeo_direccion": "ARRIBA",
                "activo": activo,
                "creado_en": MOMENTO_VENTA,
                "actualizado_en": MOMENTO_VENTA,
            },
        )
        return lista_id

    def crear_producto(self, nombre: str, *, unidades_caja: int = 12) -> tuple[UUID, UUID]:
        """Un producto con una sola presentación de venta, la de referencia."""
        producto_id = crear_producto_sql(self.sesion, self.org, nombre=nombre)
        caja_id = crear_presentacion_referencia_sql(
            self.sesion, self.org, producto_id, unidades_base=unidades_caja
        )
        return producto_id, caja_id

    def comprar(
        self, producto_id: UUID, cantidad: int, costo: str, ubicacion_id: UUID | None = None
    ) -> None:
        """Ingreso `COMPRA` con costo (fija el promedio, CST-11)."""
        stock_service.registrar_movimientos(
            self.org,
            self.sesion,
            RELOJ_VENTA,
            lineas=[
                LineaDeMovimiento(
                    producto_id=producto_id,
                    ubicacion_id=ubicacion_id or self.deposito_id,
                    cantidad_base=cantidad,
                    tipo="COMPRA",
                    costo_unitario=costo,
                    origen_tipo="COMPRA",
                    origen_id=uuid4(),
                )
            ],
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            operation_id=uuid4(),
            occurred_at=MOMENTO_VENTA,
        )

    def siguiente_numero(self) -> str:
        self._correlativo += 1
        return f"{self.prefijo}-{self._correlativo:06d}"

    # --- comandos -------------------------------------------------------------------

    def linea(
        self,
        producto_id: UUID | None = None,
        presentacion_id: UUID | None = None,
        cantidad: int = 15,
        *,
        unidades_presentacion: int = 1,
        precio: str = PRECIO_VINO,
        unidades_referencia: int = 6,
        version_id: UUID | None = None,
        bruto: str | None = None,
        **cambios: object,
    ) -> dict[str, Any]:
        """Una línea del contenido con los valores que vio el usuario (por defecto 15 botellas
        de Vino A a $12.500 la caja x6 = `31250.00`)."""
        if bruto is None:
            esperado = (
                Decimal(precio) * cantidad * unidades_presentacion / unidades_referencia
            ).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
            bruto = str(esperado)
        cuerpo: dict[str, Any] = {
            "linea_id": str(uuid4()),
            "producto_id": str(producto_id or self.vino_id),
            "presentacion_id": str(presentacion_id or self.botella_id),
            "cantidad": cantidad,
            "lista_version_id": str(version_id or self.version_id),
            "precio_referencia": precio,
            "unidades_referencia": unidades_referencia,
            "importe_bruto": bruto,
        }
        cuerpo.update(cambios)
        return cuerpo

    def contenido(self, *lineas: dict[str, Any], **cambios: object) -> dict[str, Any]:  # type: ignore[override]
        """El contenido de `VENTA_CONFIRMAR`: sin cobranza, a Kiosco La Esquina, desde el
        depósito. Sin `lineas`, 15 botellas de Vino A (`31250.00`)."""
        todas = list(lineas) or [self.linea()]
        total = sum((Decimal(linea["importe_bruto"]) for linea in todas), Decimal("0.00"))
        cuerpo: dict[str, Any] = {
            "venta_id": str(uuid4()),
            "numero": self.siguiente_numero(),
            "cliente_id": str(self.cliente_id),
            "ubicacion_id": str(self.deposito_id),
            "lineas": todas,
            "total": str(total),
        }
        cuerpo.update(cambios)
        return cuerpo

    def credito_offline(
        self,
        *,
        limite: str | None = None,
        saldo: str | None = "150000.00",
        politica: str | None = "ADVERTIR",
        resolucion: str | None = "SIN_EXCESO",
        autorizador_id: UUID | None = None,
    ) -> dict[str, Any]:
        """El objeto `credito` de una venta sin conexión (change 18b, D7; obligatorio, decisión del
        usuario del 2026-10-23): la evaluación del dispositivo. Por defecto, Kiosco La Esquina sin
        límite (sin control) con el saldo de la siembra y `SIN_EXCESO`."""
        return {
            "limite": limite,
            "saldo_considerado": saldo,
            "politica": politica,
            "resolucion": resolucion,
            "autorizador_id": None if autorizador_id is None else str(autorizador_id),
        }

    def cobranza(self, *medios: tuple[UUID, str, str | None]) -> dict[str, Any]:
        """El bloque `cobranza` del contenido; por defecto, `20000.00` en efectivo."""
        return {
            "cobranza_id": str(uuid4()),
            "medios": self.medios(*(medios or ((self.efectivo_id, "20000.00", None),))),
        }

    def sobre(  # type: ignore[override]
        self,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        tipo: str = VENTA_CONFIRMAR,
        jornada_id: UUID | None = None,
        organizacion_id: UUID | None = None,
        occurred_at: datetime | None = None,
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=organizacion_id or self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=occurred_at or MOMENTO_VENTA,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
            jornada_id=jornada_id,
        )

    def enviar(  # type: ignore[override]
        self,
        contenido: dict[str, Any] | None = None,
        *,
        operation_id: UUID | None = None,
        tipo: str = VENTA_CONFIRMAR,
        jornada_id: UUID | None = None,
        occurred_at: datetime | None = None,
        credenciales: tuple[CredencialDePin, ...] = (),
    ) -> Comando:
        sobre = self.sobre(
            contenido if contenido is not None else self.contenido(),
            operation_id=operation_id,
            tipo=tipo,
            jornada_id=jornada_id,
            occurred_at=occurred_at,
        )
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: registro.SesionDeHandler) -> sync_service.ResultadoHandler:
            # Solo el handler de la venta recibe el dato efímero de D2 (los demás no lo declaran).
            extra: dict[str, Any] = {"credenciales": credenciales} if credenciales else {}
            if sobre.tipo == VENTA_CONFIRMAR:
                extra = {"credenciales": credenciales}
            return registrado.funcion(  # type: ignore[no-any-return]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ_VENTA, **extra
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ_VENTA, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def vender(
        self,
        *lineas: dict[str, Any],
        credenciales: tuple[CredencialDePin, ...] = (),
        **cambios: object,
    ) -> Comando:
        return self.enviar(self.contenido(*lineas, **cambios), credenciales=credenciales)

    # --- descuentos y crédito (change 18b) -------------------------------------------

    def permitir(self, *permisos: str, usuario_id: UUID | None = None) -> None:
        """Le suma permisos al rol del usuario (por defecto, el de quien vende)."""
        rol_id = self.sesion.scalar(
            text("SELECT rol_id FROM usuario WHERE organizacion_id = :o AND id = :u"),
            {"o": self.org, "u": usuario_id or self.usuario_id},
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, self.sesion, rol_id=rol_id, permiso_codigo=codigo
            )
        self.sesion.commit()

    def fijar_tope(self, tope: str, *, usuario_id: UUID | None = None) -> None:
        """Tope de descuento del rol del usuario (fracción como texto: `"0.05"` = 5 %)."""
        self.sesion.execute(
            text(
                "UPDATE rol SET tope_descuento = :t WHERE organizacion_id = :o AND id = "
                "(SELECT rol_id FROM usuario WHERE organizacion_id = :o AND id = :u)"
            ),
            {"t": Decimal(tope), "o": self.org, "u": usuario_id or self.usuario_id},
        )
        self.sesion.commit()

    def crear_usuario(
        self,
        permisos: frozenset[str],
        *,
        pin: str | None = None,
        tope: str = "0",
        org: UUID | None = None,
    ) -> UUID:
        """Otro usuario (en `org`, por defecto la del entorno) con un rol propio y, si se pide,
        un PIN de autorización definido."""
        organizacion = org or self.org
        rol = identidad_repository.crear_rol(
            organizacion,
            self.sesion,
            rol_id=nuevo_id(),
            nombre=f"Rol {uuid4().hex[:6]}",
            tope_descuento=Decimal(tope),
            activo=True,
            momento=MOMENTO_VENTA,
        )
        for codigo in sorted(permisos):
            identidad_repository.asignar_permiso_a_rol(
                organizacion, self.sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        usuario = identidad_repository.crear_usuario(
            organizacion,
            self.sesion,
            usuario_id=nuevo_id(),
            usuario=f"u-{uuid4().hex[:8]}",
            nombre="Supervisor de prueba",
            email=None,
            password_hash="hash",
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO_VENTA,
        )
        if pin is not None:
            # El PIN se define una hora antes de la venta: su fila marcador reinicia el contador
            # de fallos y los fallos de la venta tienen que ser posteriores (ADR-011, D3).
            identidad_service.establecer_pin_autorizacion(
                organizacion,
                self.sesion,
                FixedClock(MOMENTO_VENTA - timedelta(hours=1)),
                usuario_id=usuario.id,
                pin=pin,
                actor_id=usuario.id,
            )
        self.sesion.commit()
        return usuario.id

    def otra_organizacion(self) -> UUID:
        organizacion = crear_organizacion(self.sesion).id
        self.sesion.commit()
        return organizacion

    def credencial(self, autorizador_id: UUID, pin: str) -> CredencialDePin:
        return CredencialDePin(autorizador_id=autorizador_id, pin=SecretStr(pin))

    def crear_regla(
        self,
        *,
        porcentaje: str = "0.050000",
        umbral: str = "20",
        medida: str = "CAJAS_EQUIVALENTES",
        estado: str = "ACTIVA",
        desde: datetime | None = None,
        hasta: datetime | None = None,
        prioridad: int = 1,
        acumulable: bool = False,
    ) -> UUID:
        """Una regla de volumen sobre toda la venta ("cajas equivalentes >= 20 -> 5 %")."""
        regla_id = uuid4()
        if estado != "BORRADOR" and desde is None:
            desde = MOMENTO_VENTA - timedelta(days=30)
        insertar_sql(
            self.sesion,
            "regla_descuento",
            {
                "id": regla_id,
                "organizacion_id": self.org,
                "nombre": f"Regla {regla_id.hex[:6]}",
                "tipo": "VOLUMEN_OPERACION",
                "medida": medida,
                "operador": "GTE",
                "umbral": Decimal(umbral),
                "accion_tipo": "PORCENTAJE",
                "accion_porcentaje": Decimal(porcentaje),
                "accion_importe": None,
                "prioridad": prioridad,
                "acumulable": acumulable,
                "vigencia_desde": desde,
                "vigencia_hasta": hasta,
                "estado": estado,
                "creado_en": MOMENTO_VENTA,
                "actualizado_en": MOMENTO_VENTA,
            },
        )
        self.sesion.commit()
        return regla_id

    def pausar_regla(self, regla_id: UUID) -> None:
        self.sesion.execute(
            text(
                "UPDATE regla_descuento SET estado = 'PAUSADA' "
                "WHERE organizacion_id = :o AND id = :r"
            ),
            {"o": self.org, "r": regla_id},
        )
        self.sesion.commit()

    def datos_de_credito(
        self,
        cliente_id: UUID | None = None,
        *,
        limite: str | None,
        politica: str | None = None,
    ) -> None:
        """Límite y política propios del cliente (por defecto, Kiosco La Esquina)."""
        self.actualizar_cliente(
            cliente_id or self.cliente_id,
            limite_credito=None if limite is None else Decimal(limite),
            politica_credito=politica,
        )
        self.sesion.commit()

    def producto_a(self, precio: str, *, stock: int = 1000, costo: str = "10") -> tuple[UUID, UUID]:
        """Un producto de una sola presentación de una unidad al `precio`, con stock y costo.
        Devuelve `(producto_id, presentacion_id)`."""
        producto_id, presentacion_id = self.crear_producto(f"Producto a {precio}", unidades_caja=1)
        self.poner_precio(self.version_id, producto_id, precio, 1)
        self.comprar(producto_id, stock, costo)
        self.sesion.commit()
        return producto_id, presentacion_id

    def descuentos_de_venta(self) -> list[VentaLineaDescuento]:
        """Todas las filas de `venta_linea_descuento` de la organización, por línea y orden."""
        self.sesion.expire_all()
        return list(
            self.sesion.scalars(
                select(VentaLineaDescuento)
                .where(VentaLineaDescuento.organizacion_id == self.org)
                .order_by(VentaLineaDescuento.venta_linea_id, VentaLineaDescuento.orden)
            ).all()
        )

    def intentos_de_pin(self) -> int:
        """Filas de fallos del PIN (lo único que puede quedar escrito tras un rechazo)."""
        self.sesion.rollback()
        return int(
            self.sesion.scalar(
                text(
                    "SELECT count(*) FROM intento_pin_autorizacion "
                    "WHERE organizacion_id = :o AND NOT exito"
                ),
                {"o": self.org},
            )
            or 0
        )

    # --- lecturas -------------------------------------------------------------------

    def ventas(self) -> list[Venta]:
        self.sesion.expire_all()
        return list(
            self.sesion.scalars(
                select(Venta).where(Venta.organizacion_id == self.org).order_by(Venta.creado_en)
            ).all()
        )

    def lineas_de_venta(self, venta_id: UUID) -> list[VentaLinea]:
        return list(
            self.sesion.scalars(
                select(VentaLinea)
                .where(VentaLinea.organizacion_id == self.org, VentaLinea.venta_id == venta_id)
                .order_by(VentaLinea.orden)
            ).all()
        )

    def movimientos_de_stock(self, tipo: str = "VENTA") -> list[StockMovimiento]:
        return list(
            self.sesion.scalars(
                select(StockMovimiento)
                .where(StockMovimiento.organizacion_id == self.org, StockMovimiento.tipo == tipo)
                .order_by(StockMovimiento.registered_at, StockMovimiento.id)
            ).all()
        )

    def stock(self, producto_id: UUID | None = None, ubicacion_id: UUID | None = None) -> int:
        self.sesion.expire_all()
        return stock_service.obtener_saldo(
            self.org,
            self.sesion,
            producto_id=producto_id or self.vino_id,
            ubicacion_id=ubicacion_id or self.deposito_id,
        )

    def costo(self, producto_id: UUID | None = None) -> CostoProducto:
        return self.sesion.scalars(
            select(CostoProducto)
            .where(
                CostoProducto.organizacion_id == self.org,
                CostoProducto.producto_id == (producto_id or self.vino_id),
            )
            .execution_options(populate_existing=True)
        ).one()

    def ultimo_correlativo(self) -> int:
        self.sesion.expire_all()
        return int(
            self.sesion.scalar(
                select(Dispositivo.ultimo_correlativo).where(
                    Dispositivo.organizacion_id == self.org, Dispositivo.id == self.dispositivo_id
                )
            )
            or 0
        )

    def cantidad_de_comandos(self) -> int:
        return int(
            self.sesion.scalar(
                select(func.count()).select_from(Comando).where(Comando.organizacion_id == self.org)
            )
            or 0
        )

    def sin_efectos_de_venta(self, *, stock_esperado: int = 48, saldo: str = "150000.00") -> None:
        """Nada quedó escrito por la venta (INV-01): ni venta ni líneas, ni egreso de stock, ni
        movimiento `VENTA` o `COBRANZA` de la cuenta, ni cobranza; el stock, el promedio, el saldo
        y el correlativo siguen como los dejó el entorno."""
        self.sesion.rollback()
        assert self.ventas() == []
        assert self.movimientos_de_stock("VENTA") == []
        assert self.movimientos("VENTA") == []
        assert self.movimientos("COBRANZA") == []
        assert self.cobranzas() == []
        assert self.stock() == stock_esperado
        assert self.saldo() == Decimal(saldo)
        assert self.ultimo_correlativo() == 0
