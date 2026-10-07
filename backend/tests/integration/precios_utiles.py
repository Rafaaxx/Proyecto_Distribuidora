"""Entorno compartido de las pruebas de `precios` (change 13): una organización con su
usuario, un producto con categoría, marca y proveedor, y los atajos para enviar los
comandos por el bus (`sync_service.procesar_comando`, que maneja la transacción)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.clientes import (
    commands as _clientes_commands,  # noqa: F401 (handlers y verificador)
)
from app.modules.clientes.models import Cliente
from app.modules.identidad.models import Auditoria
from app.modules.precios import commands as _precios_commands  # noqa: F401 (registra los handlers)
from app.modules.precios.models import ListaPrecio, ListaVersion, PrecioItem, ReglaMargen
from app.modules.proveedores import commands as _proveedores_commands  # noqa: F401
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from tests.integration.stock_utiles import (
    crear_presentacion_referencia_sql,
    crear_presentacion_sql,
    crear_producto_sql,
)

MOMENTO = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

LISTA_CREAR = "LISTA_PRECIO_CREAR"
LISTA_MODIFICAR = "LISTA_PRECIO_MODIFICAR"
REGLA_CREAR = "REGLA_MARGEN_CREAR"
REGLA_MODIFICAR = "REGLA_MARGEN_MODIFICAR"
REDONDEO_DEFINIR = "REDONDEO_CATEGORIA_DEFINIR"
GENERAR_BORRADOR = "LISTA_GENERAR_BORRADOR"
PRECIO_FIJAR = "LISTA_BORRADOR_PRECIO_FIJAR"
PUBLICAR = "LISTA_PUBLICAR"
ANULAR_VERSION = "LISTA_ANULAR_VERSION"

LISTA_PREDETERMINADA_DEFINIR = "LISTA_PRECIO_PREDETERMINADA_DEFINIR"
CLIENTE_CREAR = "CLIENTE_CREAR"
CLIENTE_MODIFICAR = "CLIENTE_MODIFICAR"

PERMISOS = frozenset({"GESTIONAR_LISTAS"})


class _Ausente:
    """Marca "el campo no viaja" (distinta de `None`, que viaja como nulo)."""


AUSENTE = _Ausente()


class Entorno:
    """Una organización con un usuario con `permisos`, un producto (`Vino A`, referencia
    `Caja x6`) con su categoría y proveedor, y una marca."""

    def __init__(self, sesion: Session, *, permisos: frozenset[str] = PERMISOS) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        self.proveedor_id = crear_proveedor(sesion, self.org, nombre="Bodega Sur")
        self.vino_id = crear_producto_sql(
            sesion, self.org, nombre="Vino A", proveedor_id=self.proveedor_id
        )
        self.vino_presentacion_id = crear_presentacion_referencia_sql(
            sesion, self.org, self.vino_id, unidades_base=6
        )
        self.categoria_id = sesion.execute(
            text("SELECT categoria_id FROM producto WHERE id = :p"), {"p": self.vino_id}
        ).scalar_one()
        self.marca_id = self.crear_marca("Bodega Norte")
        sesion.flush()

    def actuar_con_permisos(self, permisos: frozenset[str]) -> None:
        """Los comandos siguientes los envía otro usuario de la misma organización, con
        `permisos`."""
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            self.sesion, self.org, permisos=permisos
        )

    def crear_marca(self, nombre: str, *, org: UUID | None = None) -> UUID:
        marca_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO marca (id, organizacion_id, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :nombre, true, :m, :m)"
            ),
            {"id": marca_id, "org": org or self.org, "nombre": nombre, "m": MOMENTO},
        )
        return marca_id

    def crear_categoria(self, nombre: str) -> UUID:
        categoria_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO categoria (id, organizacion_id, nombre, activo, creado_en, "
                "actualizado_en) VALUES (:id, :org, :nombre, true, :m, :m)"
            ),
            {"id": categoria_id, "org": self.org, "nombre": nombre, "m": MOMENTO},
        )
        return categoria_id

    def crear_producto(
        self,
        nombre: str,
        *,
        unidades_base: int = 6,
        categoria_id: UUID | None = None,
        marca_id: UUID | None = None,
        proveedor_id: UUID | None = None,
    ) -> UUID:
        """Un producto activo con su presentación de referencia `Caja x{unidades_base}`."""
        producto_id = crear_producto_sql(
            self.sesion, self.org, nombre=nombre, proveedor_id=proveedor_id or self.proveedor_id
        )
        crear_presentacion_referencia_sql(
            self.sesion, self.org, producto_id, unidades_base=unidades_base
        )
        if categoria_id is not None:
            self.sesion.execute(
                text("UPDATE producto SET categoria_id = :c WHERE id = :p"),
                {"c": categoria_id, "p": producto_id},
            )
        if marca_id is not None:
            self.sesion.execute(
                text("UPDATE producto SET marca_id = :m WHERE id = :p"),
                {"m": marca_id, "p": producto_id},
            )
        return producto_id

    def crear_producto_sin_referencia(self, nombre: str) -> UUID:
        """Un producto activo SIN presentación de referencia (solo una `Unidad` que no lo es):
        el caso que `precios` informa como `SIN_PRESENTACION_DE_REFERENCIA`."""
        producto_id = crear_producto_sql(
            self.sesion, self.org, nombre=nombre, proveedor_id=self.proveedor_id
        )
        crear_presentacion_sql(self.sesion, self.org, producto_id, nombre="Unidad", unidades_base=1)
        return producto_id

    def presentacion_de_referencia(self, producto_id: UUID) -> UUID:
        """La referencia del producto; si no tiene (`crear_producto_sin_referencia`), su única
        presentación, para poder informarle un costo."""
        return self.sesion.execute(
            text(
                "SELECT id FROM presentacion WHERE producto_id = :p "
                "ORDER BY es_referencia DESC, id LIMIT 1"
            ),
            {"p": producto_id},
        ).scalar_one()

    def crear_presentacion(self, producto_id: UUID, nombre: str, unidades_base: int) -> UUID:
        return crear_presentacion_sql(
            self.sesion, self.org, producto_id, nombre=nombre, unidades_base=unidades_base
        )

    def informar_costo(
        self,
        producto_id: UUID,
        costo_base: str,
        *,
        presentacion_id: UUID | None = None,
        vigencia: date | None = None,
        computa: bool = True,
        creado_en: datetime = MOMENTO,
        proveedor_id: UUID | None = None,
    ) -> UUID:
        """Inserta un costo informado con `costo_base` por unidad base (CST-03). La fecha de
        vigencia es la de hoy (`MOMENTO`) salvo que se pase otra."""
        costo_id = uuid4()
        presentacion = presentacion_id or self.presentacion_de_referencia(producto_id)
        self.sesion.execute(
            text(
                "INSERT INTO costo_informado (id, organizacion_id, proveedor_id, producto_id, "
                "presentacion_id, valor, incluye_iva, computa_credito_fiscal, bonificacion, "
                "alicuota_aplicada, costo_base, vigencia_desde, operation_id, usuario_id, "
                "creado_en) VALUES (:id, :org, :prov, :prod, :pres, :base, false, :comp, 0, "
                "0.21, :base, :vig, :op, :usr, :creado)"
            ),
            {
                "id": costo_id,
                "org": self.org,
                "prov": proveedor_id or self.proveedor_id,
                "prod": producto_id,
                "pres": presentacion,
                "base": costo_base,
                "comp": computa,
                "vig": vigencia or MOMENTO.date(),
                "op": uuid4(),
                "usr": self.usuario_id,
                "creado": creado_en,
            },
        )
        return costo_id

    # --- envío de comandos ------------------------------------------------------------

    def sobre(
        self,
        tipo: str,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        modo: str = "ONLINE",
    ) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,  # type: ignore[arg-type]
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )

    def enviar(
        self, tipo: str, contenido: dict[str, Any], *, operation_id: UUID | None = None
    ) -> Comando:
        sobre = self.sobre(tipo, contenido, operation_id=operation_id)
        huella = calcular_huella(sobre.contenido)
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
            return registrado.funcion(  # type: ignore[call-arg,return-value]
                sobre, validado, sesion=sesion_protegida, reloj=RELOJ
            )

        return sync_service.procesar_comando(
            self.sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
        )

    def crear_lista(
        self, nombre: str = "General", multiplo: str = "100.00", direccion: str = "ARRIBA"
    ) -> UUID:
        comando = self.enviar(
            LISTA_CREAR,
            {"nombre": nombre, "redondeo_multiplo": multiplo, "redondeo_direccion": direccion},
        )
        assert comando.resultado is not None
        return UUID(str(comando.resultado["lista_id"]))

    def crear_regla(
        self,
        lista_id: UUID,
        *,
        tipo: str = "MARKUP",
        valor: str = "0.300000",
        alcance_tipo: str = "LISTA",
        alcance_id: UUID | None = None,
    ) -> UUID:
        comando = self.enviar(
            REGLA_CREAR,
            {
                "lista_id": str(lista_id),
                "tipo": tipo,
                "valor": valor,
                "alcance_tipo": alcance_tipo,
                "alcance_id": None if alcance_id is None else str(alcance_id),
            },
        )
        assert comando.resultado is not None
        return UUID(str(comando.resultado["regla_id"]))

    def generar_borrador(self, lista_id: UUID, *, operation_id: UUID | None = None) -> Comando:
        return self.enviar(GENERAR_BORRADOR, {"lista_id": str(lista_id)}, operation_id=operation_id)

    def fijar_precio(
        self,
        lista_id: UUID,
        version_id: UUID,
        producto_id: UUID,
        precio_final: str | None,
        *,
        operation_id: UUID | None = None,
    ) -> Comando:
        return self.enviar(
            PRECIO_FIJAR,
            {
                "lista_id": str(lista_id),
                "version_id": str(version_id),
                "producto_id": str(producto_id),
                "precio_final": precio_final,
            },
            operation_id=operation_id,
        )

    def publicar(
        self,
        lista_id: UUID,
        version_id: UUID,
        *,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        operation_id: UUID | None = None,
    ) -> Comando:
        return self.enviar(
            PUBLICAR,
            {
                "lista_id": str(lista_id),
                "version_id": str(version_id),
                "vigencia_desde": None if desde is None else desde.isoformat(),
                "vigencia_hasta": None if hasta is None else hasta.isoformat(),
            },
            operation_id=operation_id,
        )

    def anular_version(
        self, lista_id: UUID, version_id: UUID, *, operation_id: UUID | None = None
    ) -> Comando:
        return self.enviar(
            ANULAR_VERSION,
            {"lista_id": str(lista_id), "version_id": str(version_id)},
            operation_id=operation_id,
        )

    def desactivar_lista(
        self, lista_id: UUID, nombre: str = "General", *, operation_id: UUID | None = None
    ) -> Comando:
        return self.enviar(
            LISTA_MODIFICAR,
            {
                "lista_id": str(lista_id),
                "nombre": nombre,
                "redondeo_multiplo": "100.00",
                "redondeo_direccion": "ARRIBA",
                "activo": False,
            },
            operation_id=operation_id,
        )

    def definir_predeterminada(
        self, lista_id: UUID, *, operation_id: UUID | None = None
    ) -> Comando:
        return self.enviar(
            LISTA_PREDETERMINADA_DEFINIR, {"lista_id": str(lista_id)}, operation_id=operation_id
        )

    def predeterminada(self) -> UUID | None:
        return self.sesion.execute(
            text(
                "SELECT lista_precio_default_id FROM configuracion_organizacion "
                "WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        ).scalar_one()

    def crear_cliente(
        self,
        nombre: str = "Kiosco El Faro",
        *,
        lista_precio_id: UUID | None = None,
        operation_id: UUID | None = None,
    ) -> UUID:
        """`CLIENTE_CREAR` por el bus (el usuario necesita `GESTIONAR_CLIENTES`)."""
        comando = self.enviar(
            CLIENTE_CREAR,
            {
                "nombre": nombre,
                "direccion": "Av. San Martín 1420",
                "contacto": "Rocío",
                "lista_precio_id": None if lista_precio_id is None else str(lista_precio_id),
            },
            operation_id=operation_id,
        )
        assert comando.resultado is not None
        return UUID(str(comando.resultado["cliente_id"]))

    def modificar_cliente(
        self,
        cliente_id: UUID,
        *,
        lista_precio_id: UUID | None | _Ausente = AUSENTE,
        estado: str = "ACTIVO",
        nombre: str = "Kiosco El Faro",
        operation_id: UUID | None = None,
    ) -> Comando:
        """`CLIENTE_MODIFICAR` por el bus. Sin `lista_precio_id` el campo no viaja en el
        contenido (conserva la lista); `None` viaja como nulo (la quita)."""
        contenido: dict[str, Any] = {
            "cliente_id": str(cliente_id),
            "nombre": nombre,
            "direccion": "Av. San Martín 1420",
            "contacto": "Rocío",
            "estado": estado,
        }
        if not isinstance(lista_precio_id, _Ausente):
            contenido["lista_precio_id"] = None if lista_precio_id is None else str(lista_precio_id)
        return self.enviar(CLIENTE_MODIFICAR, contenido, operation_id=operation_id)

    def cliente(self, cliente_id: UUID) -> Cliente:
        return self.sesion.scalars(
            select(Cliente)
            .where(Cliente.organizacion_id == self.org, Cliente.id == cliente_id)
            .execution_options(populate_existing=True)
        ).one()

    def borrador_de_general(self, nombre: str = "General") -> tuple[UUID, UUID]:
        """Una lista con margen bruto 30% y redondeo a 100 hacia arriba, Vino A con costo
        base 1000 y su borrador generado: Vino A a `8600.00`."""
        lista_id = self.crear_lista(nombre, "100.00", "ARRIBA")
        self.crear_regla(lista_id, tipo="MARGEN_BRUTO", valor="0.300000")
        self.informar_costo(self.vino_id, "1000")
        self.generar_borrador(lista_id)
        return lista_id, self.versiones(lista_id)[-1].id

    def publicar_por_sql(
        self,
        version_id: UUID,
        *,
        desde: datetime = MOMENTO,
        hasta: datetime | None = None,
    ) -> None:
        """Deja una versión `PUBLICADA` por SQL: base de los escenarios de los borradores
        que no dependen del comando de publicación (que es del grupo 8)."""
        self.sesion.execute(
            text(
                "UPDATE lista_version SET estado = 'PUBLICADA', vigencia_desde = :d, "
                "vigencia_hasta = :h, publicado_por_id = :u, publicado_en = :d "
                "WHERE organizacion_id = :o AND id = :v"
            ),
            {"d": desde, "h": hasta, "u": self.usuario_id, "o": self.org, "v": version_id},
        )

    def informar_costo_por_comando(self, producto_id: UUID, valor: str) -> None:
        """`COSTO_INFORMAR` por el bus, con un usuario que puede registrar compras."""
        usuario, dispositivo = self.usuario_id, self.dispositivo_id
        self.actuar_con_permisos(frozenset({"REGISTRAR_COMPRA"}))
        try:
            self.enviar(
                "COSTO_INFORMAR",
                {
                    "proveedor_id": str(self.proveedor_id),
                    "costos": [
                        {
                            "producto_id": str(producto_id),
                            "presentacion_id": str(self.presentacion_de_referencia(producto_id)),
                            "valor": valor,
                            "incluye_iva": False,
                            "vigencia_desde": MOMENTO.date().isoformat(),
                        }
                    ],
                },
            )
        finally:
            self.usuario_id, self.dispositivo_id = usuario, dispositivo

    def cambiar_modo_impositivo(self, modo: str) -> None:
        self.sesion.execute(
            text(
                "UPDATE configuracion_organizacion SET modo_impositivo = :m "
                "WHERE organizacion_id = :o"
            ),
            {"m": modo, "o": self.org},
        )

    # --- lecturas de lo escrito --------------------------------------------------------

    def listas(self, *, org: UUID | None = None) -> list[ListaPrecio]:
        consulta = select(ListaPrecio).where(ListaPrecio.organizacion_id == (org or self.org))
        return list(self.sesion.scalars(consulta.order_by(ListaPrecio.nombre)))

    def reglas(self, lista_id: UUID) -> list[ReglaMargen]:
        consulta = select(ReglaMargen).where(
            ReglaMargen.organizacion_id == self.org, ReglaMargen.lista_id == lista_id
        )
        return list(self.sesion.scalars(consulta.order_by(ReglaMargen.creado_en, ReglaMargen.id)))

    def versiones(self, lista_id: UUID) -> list[ListaVersion]:
        consulta = select(ListaVersion).where(
            ListaVersion.organizacion_id == self.org, ListaVersion.lista_id == lista_id
        )
        return list(self.sesion.scalars(consulta.order_by(ListaVersion.numero)))

    def precios(self, version_id: UUID) -> dict[UUID, PrecioItem]:
        """Los precios de una versión por producto (PRC-10: uno solo por producto)."""
        consulta = select(PrecioItem).where(
            PrecioItem.organizacion_id == self.org, PrecioItem.version_id == version_id
        )
        return {
            precio.producto_id: precio
            for precio in self.sesion.scalars(consulta.execution_options(populate_existing=True))
        }

    def auditorias(self, accion: str) -> list[Auditoria]:
        consulta = select(Auditoria).where(
            Auditoria.organizacion_id == self.org, Auditoria.accion == accion
        )
        return list(self.sesion.scalars(consulta))

    def comandos(self) -> list[Comando]:
        return list(self.sesion.scalars(select(Comando).where(Comando.organizacion_id == self.org)))

    def cantidad(self, tabla: str) -> int:
        return int(
            self.sesion.execute(
                text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"), {"o": self.org}
            ).scalar_one()
        )
