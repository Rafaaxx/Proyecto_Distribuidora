"""Change 05, tarea 8.3: integración de los handlers de `catalogo` con el
bus real (`sync_service.procesar_comando`, PostgreSQL real). Representativo
en dos tipos (`CATEGORIA_CREAR`, simple, y `PRODUCTO_CREAR`, con escritura
de múltiples filas en una transacción): el mecanismo del bus (reserva,
huella, auditoría, reintentos) es genérico y ya está probado
exhaustivamente para `identidad` (`test_bus_transaccion.py`); acá se
confirma que los HANDLERS de catálogo se integran correctamente con él,
sin repetir la matriz completa de 9 tipos × 4 escenarios.

Escenarios (tarea 8.3): aceptado deja una sola fila de auditoría
`origen = COMANDO` con su `operation_id`; reenvío idéntico no duplica;
mismo `operation_id` con contenido distinto -> `COMANDO_INCONSISTENTE`;
un error de dominio revierte la reserva y permite reintentar corregido.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.errores import ComandoInconsistenteError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.ids import nuevo_id
from app.modules.catalogo import commands as catalogo_commands
from app.modules.catalogo import repository as catalogo_repository
from app.modules.catalogo.domain.errores import (
    CodigoDuplicadoError,
    NombreDuplicadoError,
    NombreInvalidoError,
    ReferenciaInvalidaError,
    UnidadesInvalidasError,
)
from app.modules.configuracion.models import AlicuotaIva
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Auditoria, Organizacion
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)


def _crear_organizacion(sesion: Session) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba catálogo",
        slug=f"org-catalogo-{uuid4().hex[:8]}",
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
    return organizacion


def _crear_usuario_y_dispositivo(sesion: Session, organizacion_id: UUID) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Gestor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"gestor-{uuid4().hex[:8]}",
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
        prefijo=f"B{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _sobre(
    *,
    tipo: str,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    operation_id: UUID,
    contenido: dict[str, object],
) -> SobreComando:
    return SobreComando(
        operation_id=operation_id,
        tipo=tipo,
        version=1,
        modo="ONLINE",
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido,  # type: ignore[arg-type]
    )


def _contar_auditoria(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Auditoria).where(Auditoria.operation_id == operation_id)
    )


def _procesar_categoria_crear(sesion: Session, sobre: SobreComando) -> Comando:
    huella = calcular_huella(sobre.contenido)
    contenido_validado = catalogo_commands.CategoriaCrearContenidoV1.model_validate(sobre.contenido)

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_categoria_crear(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=RELOJ
        )

    return sync_service.procesar_comando(
        sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def test_categoria_crear_aceptado_deja_una_sola_fila_de_auditoria(db_session: Session) -> None:
    organizacion = _crear_organizacion(db_session)
    usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
    db_session.commit()

    operation_id = uuid4()
    sobre = _sobre(
        tipo="CATEGORIA_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        contenido={"nombre": "Vinos"},
    )

    comando = _procesar_categoria_crear(db_session, sobre)

    assert comando.estado == "ACEPTADO"
    assert _contar_auditoria(db_session, operation_id) == 1
    categorias = catalogo_repository.listar_categorias(organizacion.id, db_session)
    assert [c.nombre for c in categorias] == ["Vinos"]


def test_reenvio_identico_no_duplica(db_session: Session) -> None:
    organizacion = _crear_organizacion(db_session)
    usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
    db_session.commit()

    operation_id = uuid4()
    sobre = _sobre(
        tipo="CATEGORIA_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        contenido={"nombre": "Vinos"},
    )

    primero = _procesar_categoria_crear(db_session, sobre)
    segundo = _procesar_categoria_crear(db_session, sobre)

    assert primero.resultado == segundo.resultado
    assert _contar_auditoria(db_session, operation_id) == 1
    categorias = catalogo_repository.listar_categorias(organizacion.id, db_session)
    assert len(categorias) == 1


def test_mismo_operation_id_con_contenido_distinto_es_inconsistente(
    db_session: Session,
) -> None:
    organizacion = _crear_organizacion(db_session)
    usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
    db_session.commit()

    operation_id = uuid4()
    primero = _sobre(
        tipo="CATEGORIA_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        contenido={"nombre": "Vinos"},
    )
    _procesar_categoria_crear(db_session, primero)

    segundo = _sobre(
        tipo="CATEGORIA_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        contenido={"nombre": "Licores"},
    )
    with pytest.raises(ComandoInconsistenteError):
        _procesar_categoria_crear(db_session, segundo)

    categorias = catalogo_repository.listar_categorias(organizacion.id, db_session)
    assert [c.nombre for c in categorias] == ["Vinos"]


def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar_corregido(
    db_session: Session,
) -> None:
    """`NOMBRE_DUPLICADO`: el primer `CATEGORIA_CREAR` deja "Vinos"; un
    segundo comando (`operation_id` DISTINTO) con el mismo nombre falla y
    NO deja reserva de comando ni fila de auditoría (INV-01, `02` §6.3);
    reintentando ese mismo `operation_id` con contenido corregido, se
    acepta."""
    organizacion = _crear_organizacion(db_session)
    usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
    db_session.commit()

    _procesar_categoria_crear(
        db_session,
        _sobre(
            tipo="CATEGORIA_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=uuid4(),
            contenido={"nombre": "Vinos"},
        ),
    )

    operation_id_fallido = uuid4()
    sobre_fallido = _sobre(
        tipo="CATEGORIA_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id_fallido,
        contenido={"nombre": "Vinos"},
    )
    with pytest.raises(NombreDuplicadoError):
        _procesar_categoria_crear(db_session, sobre_fallido)

    assert _contar_auditoria(db_session, operation_id_fallido) == 0
    reserva_previa = db_session.scalar(
        select(func.count())
        .select_from(Comando)
        .where(Comando.operation_id == operation_id_fallido)
    )
    assert reserva_previa == 0

    sobre_corregido = _sobre(
        tipo="CATEGORIA_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id_fallido,
        contenido={"nombre": "Licores"},
    )
    comando = _procesar_categoria_crear(db_session, sobre_corregido)
    assert comando.estado == "ACEPTADO"


# --- PRODUCTO_CREAR: representativo de una escritura multi-fila -----------


def _procesar_producto_crear(sesion: Session, sobre: SobreComando) -> Comando:
    huella = calcular_huella(sobre.contenido)
    contenido_validado = catalogo_commands.ProductoCrearContenidoV1.model_validate(sobre.contenido)

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return catalogo_commands.manejar_producto_crear(
            sobre, contenido_validado, sesion=sesion_protegida, reloj=RELOJ
        )

    return sync_service.procesar_comando(
        sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def test_producto_crear_aceptado_deja_producto_y_presentaciones_con_una_auditoria(
    db_session: Session,
) -> None:
    organizacion = _crear_organizacion(db_session)
    usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=organizacion.id,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    db_session.add(alicuota)
    categoria = catalogo_repository.crear_categoria(
        organizacion.id,
        db_session,
        categoria_id=nuevo_id(),
        nombre="Vinos",
        activo=True,
        momento=MOMENTO,
    )
    db_session.commit()

    operation_id = uuid4()
    sobre = _sobre(
        tipo="PRODUCTO_CREAR",
        organizacion_id=organizacion.id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        operation_id=operation_id,
        contenido={
            "codigo": "VA-001",
            "nombre": "Vino A",
            "categoria_id": str(categoria.id),
            "marca_id": None,
            "unidad_base": "botella",
            "alicuota_id": str(alicuota.id),
            "presentaciones": [
                {
                    "nombre": "Botella",
                    "unidades_base": 1,
                    "usar_en_venta": True,
                    "usar_en_compra": True,
                    "es_referencia": False,
                },
                {
                    "nombre": "Caja x6",
                    "unidades_base": 6,
                    "usar_en_venta": True,
                    "usar_en_compra": True,
                    "es_referencia": True,
                },
            ],
        },
    )

    comando = _procesar_producto_crear(db_session, sobre)

    assert comando.estado == "ACEPTADO"
    assert _contar_auditoria(db_session, operation_id) == 1
    assert comando.resultado is not None
    producto_id = UUID(str(comando.resultado["producto_id"]))
    presentaciones = catalogo_repository.listar_presentaciones_de_producto(
        organizacion.id, producto_id, db_session
    )
    assert len(presentaciones) == 2
    referencia = catalogo_repository.obtener_referencia_de_producto(
        organizacion.id, producto_id, db_session
    )
    assert referencia is not None
    assert referencia.nombre == "Caja x6"


# --- tarea 8.3 (extensión): los 7 tipos restantes contra el bus real -------
#
# Decisión del usuario 2026-09-22: extender la cobertura de la tarea 8.3 a
# los 9 tipos (antes solo 2), sin repetir código. Cada tipo obtiene DOS
# pruebas: (1) aceptado dejando una sola fila de auditoría Y reenvío
# idéntico sin duplicar (mismo mecanismo genérico del bus, así que se
# confirman juntas, como ya hacían `test_categoria_crear_aceptado_...` y
# `test_reenvio_identico_no_duplica` por separado para CATEGORIA_CREAR -- acá
# se fusionan para no multiplicar por 7 la cantidad de fixtures de
# precondición); (2) un error de dominio revierte la reserva (sin fila de
# auditoría, sin fila de `comando`) y el mismo `operation_id` puede
# reintentarse corregido.


def _procesar(
    sesion: Session,
    sobre: SobreComando,
    *,
    handler: object,
    contenido_cls: object,
) -> Comando:
    """Generaliza `_procesar_categoria_crear`/`_procesar_producto_crear` a
    cualquiera de los 9 handlers: valida el contenido con su esquema y lo
    ejecuta contra el bus real."""
    huella = calcular_huella(sobre.contenido)
    contenido_validado = contenido_cls.model_validate(sobre.contenido)  # type: ignore[attr-defined]

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return handler(  # type: ignore[operator]
            sobre, contenido_validado, sesion=sesion_protegida, reloj=RELOJ
        )

    return sync_service.procesar_comando(
        sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def _reserva_de_comando(sesion: Session, operation_id: UUID) -> int:
    return sesion.scalar(
        select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)
    )


def _crear_alicuota(sesion: Session, organizacion_id: UUID) -> AlicuotaIva:
    alicuota = AlicuotaIva(
        id=nuevo_id(),
        organizacion_id=organizacion_id,
        nombre="21%",
        valor="0.210000",
        activo=True,
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
    )
    sesion.add(alicuota)
    return alicuota


def _crear_producto_con_presentaciones(
    sesion: Session, organizacion_id: UUID, *, codigo: str = "VA-100"
) -> tuple[UUID, UUID, UUID, UUID]:
    """Crea (fuera del bus, directo por repositorio, como ya hacen las
    pruebas de arriba) categoría + alícuota + producto con dos
    presentaciones: una referencia ("Caja x6", activa, de venta) y una
    presentación simple ("Botella"). Devuelve
    `(categoria_id, alicuota_id, producto_id, presentacion_no_referencia_id)`.
    """
    categoria = catalogo_repository.crear_categoria(
        organizacion_id,
        sesion,
        categoria_id=nuevo_id(),
        nombre=f"Categoria {codigo}",
        activo=True,
        momento=MOMENTO,
    )
    alicuota = _crear_alicuota(sesion, organizacion_id)
    producto = catalogo_repository.crear_producto(
        organizacion_id,
        sesion,
        producto_id=nuevo_id(),
        codigo=codigo,
        nombre="Producto de prueba",
        categoria_id=categoria.id,
        marca_id=None,
        proveedor_id=None,
        unidad_base="botella",
        alicuota_id=alicuota.id,
        activo=True,
        momento=MOMENTO,
    )
    presentacion_simple = catalogo_repository.crear_presentacion(
        organizacion_id,
        sesion,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Botella",
        unidades_base=1,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=False,
        activo=True,
        momento=MOMENTO,
    )
    catalogo_repository.crear_presentacion(
        organizacion_id,
        sesion,
        presentacion_id=nuevo_id(),
        producto_id=producto.id,
        nombre="Caja x6",
        unidades_base=6,
        usar_en_venta=True,
        usar_en_compra=True,
        es_referencia=True,
        activo=True,
        momento=MOMENTO,
    )
    return categoria.id, alicuota.id, producto.id, presentacion_simple.id


class TestCategoriaModificarContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        categoria = catalogo_repository.crear_categoria(
            organizacion.id,
            db_session,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="CATEGORIA_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={"categoria_id": str(categoria.id), "nombre": "Vinos finos", "activo": True},
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_categoria_modificar,
            contenido_cls=catalogo_commands.CategoriaModificarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_categoria_modificar,
            contenido_cls=catalogo_commands.CategoriaModificarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        actualizada = catalogo_repository.obtener_categoria_por_id(
            organizacion.id, categoria.id, db_session
        )
        assert actualizada is not None
        assert actualizada.nombre == "Vinos finos"

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        categoria = catalogo_repository.crear_categoria(
            organizacion.id,
            db_session,
            categoria_id=nuevo_id(),
            nombre="Vinos",
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="CATEGORIA_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={"categoria_id": str(categoria.id), "nombre": "   ", "activo": True},
        )
        with pytest.raises(NombreInvalidoError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_categoria_modificar,
                contenido_cls=catalogo_commands.CategoriaModificarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="CATEGORIA_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={"categoria_id": str(categoria.id), "nombre": "Vinos finos", "activo": True},
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_categoria_modificar,
            contenido_cls=catalogo_commands.CategoriaModificarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


class TestMarcaCrearContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="MARCA_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={"nombre": "Nacional"},
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_marca_crear,
            contenido_cls=catalogo_commands.MarcaCrearContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_marca_crear,
            contenido_cls=catalogo_commands.MarcaCrearContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        marcas = catalogo_repository.listar_marcas(organizacion.id, db_session)
        assert [m.nombre for m in marcas] == ["Nacional"]

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        catalogo_repository.crear_marca(
            organizacion.id,
            db_session,
            marca_id=nuevo_id(),
            nombre="Nacional",
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="MARCA_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={"nombre": "Nacional"},
        )
        with pytest.raises(NombreDuplicadoError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_marca_crear,
                contenido_cls=catalogo_commands.MarcaCrearContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="MARCA_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={"nombre": "Importada"},
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_marca_crear,
            contenido_cls=catalogo_commands.MarcaCrearContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


class TestMarcaModificarContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        marca = catalogo_repository.crear_marca(
            organizacion.id,
            db_session,
            marca_id=nuevo_id(),
            nombre="Nacional",
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="MARCA_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={"marca_id": str(marca.id), "nombre": "Nacional S.A.", "activo": False},
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_marca_modificar,
            contenido_cls=catalogo_commands.MarcaModificarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_marca_modificar,
            contenido_cls=catalogo_commands.MarcaModificarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        actualizada = catalogo_repository.obtener_marca_por_id(
            organizacion.id, marca.id, db_session
        )
        assert actualizada is not None
        assert actualizada.activo is False

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        marca = catalogo_repository.crear_marca(
            organizacion.id,
            db_session,
            marca_id=nuevo_id(),
            nombre="Nacional",
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="MARCA_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={"marca_id": str(marca.id), "nombre": "  ", "activo": True},
        )
        with pytest.raises(NombreInvalidoError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_marca_modificar,
                contenido_cls=catalogo_commands.MarcaModificarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="MARCA_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={"marca_id": str(marca.id), "nombre": "Nacional S.A.", "activo": True},
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_marca_modificar,
            contenido_cls=catalogo_commands.MarcaModificarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


class TestProductoModificarContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        categoria_id, alicuota_id, producto_id, _ = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-200"
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="PRODUCTO_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "producto_id": str(producto_id),
                "codigo": "VA-200",
                "nombre": "Producto renombrado",
                "categoria_id": str(categoria_id),
                "marca_id": None,
                "unidad_base": "botella",
                "alicuota_id": str(alicuota_id),
                "activo": True,
            },
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_producto_modificar,
            contenido_cls=catalogo_commands.ProductoModificarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_producto_modificar,
            contenido_cls=catalogo_commands.ProductoModificarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        actualizado = catalogo_repository.obtener_producto_por_id(
            organizacion.id, producto_id, db_session
        )
        assert actualizado is not None
        assert actualizado.nombre == "Producto renombrado"

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        categoria_id, alicuota_id, producto_id, _ = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-300"
        )
        # Un segundo producto cuyo código se intentará "robar" para el primero.
        catalogo_repository.crear_producto(
            organizacion.id,
            db_session,
            producto_id=nuevo_id(),
            codigo="VA-301",
            nombre="Otro producto",
            categoria_id=categoria_id,
            marca_id=None,
            proveedor_id=None,
            unidad_base="botella",
            alicuota_id=alicuota_id,
            activo=True,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="PRODUCTO_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "producto_id": str(producto_id),
                "codigo": "VA-301",
                "nombre": "Producto renombrado",
                "categoria_id": str(categoria_id),
                "marca_id": None,
                "unidad_base": "botella",
                "alicuota_id": str(alicuota_id),
                "activo": True,
            },
        )
        with pytest.raises(CodigoDuplicadoError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_producto_modificar,
                contenido_cls=catalogo_commands.ProductoModificarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0

        sobre_corregido = _sobre(
            tipo="PRODUCTO_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "producto_id": str(producto_id),
                "codigo": "VA-300B",
                "nombre": "Producto renombrado",
                "categoria_id": str(categoria_id),
                "marca_id": None,
                "unidad_base": "botella",
                "alicuota_id": str(alicuota_id),
                "activo": True,
            },
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_producto_modificar,
            contenido_cls=catalogo_commands.ProductoModificarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


class TestPresentacionAgregarContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, _, producto_id, _ = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-400"
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="PRESENTACION_AGREGAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "producto_id": str(producto_id),
                "nombre": "Caja x12",
                "unidades_base": 12,
                "usar_en_venta": True,
                "usar_en_compra": True,
            },
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_presentacion_agregar,
            contenido_cls=catalogo_commands.PresentacionAgregarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_presentacion_agregar,
            contenido_cls=catalogo_commands.PresentacionAgregarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        presentaciones = catalogo_repository.listar_presentaciones_de_producto(
            organizacion.id, producto_id, db_session
        )
        assert {p.nombre for p in presentaciones} == {"Botella", "Caja x6", "Caja x12"}

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, _, producto_id, _ = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-500"
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="PRESENTACION_AGREGAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "producto_id": str(producto_id),
                "nombre": "Caja inválida",
                "unidades_base": 0,
                "usar_en_venta": True,
                "usar_en_compra": True,
            },
        )
        with pytest.raises(UnidadesInvalidasError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_presentacion_agregar,
                contenido_cls=catalogo_commands.PresentacionAgregarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0
        presentaciones = catalogo_repository.listar_presentaciones_de_producto(
            organizacion.id, producto_id, db_session
        )
        assert len(presentaciones) == 2  # nada se agregó a medias.

        sobre_corregido = _sobre(
            tipo="PRESENTACION_AGREGAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "producto_id": str(producto_id),
                "nombre": "Caja x12",
                "unidades_base": 12,
                "usar_en_venta": True,
                "usar_en_compra": True,
            },
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_presentacion_agregar,
            contenido_cls=catalogo_commands.PresentacionAgregarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


class TestPresentacionModificarContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, _, _, presentacion_id = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-600"
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="PRESENTACION_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "presentacion_id": str(presentacion_id),
                "nombre": "Botella 750ml",
                "unidades_base": 1,
                "usar_en_venta": True,
                "usar_en_compra": False,
                "activo": True,
            },
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_presentacion_modificar,
            contenido_cls=catalogo_commands.PresentacionModificarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_presentacion_modificar,
            contenido_cls=catalogo_commands.PresentacionModificarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        actualizada = catalogo_repository.obtener_presentacion_por_id(
            organizacion.id, presentacion_id, db_session
        )
        assert actualizada is not None
        assert actualizada.nombre == "Botella 750ml"
        assert actualizada.usar_en_compra is False

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        """La presentación de referencia ("Caja x6") no puede desactivarse
        (CAT-03) -- se identifica leyendo la referencia del producto, sin
        asumir el orden de creación."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, _, producto_id, _ = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-700"
        )
        referencia = catalogo_repository.obtener_referencia_de_producto(
            organizacion.id, producto_id, db_session
        )
        assert referencia is not None
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="PRESENTACION_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "presentacion_id": str(referencia.id),
                "nombre": referencia.nombre,
                "unidades_base": referencia.unidades_base,
                "usar_en_venta": True,
                "usar_en_compra": True,
                "activo": False,
            },
        )
        with pytest.raises(ReferenciaInvalidaError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_presentacion_modificar,
                contenido_cls=catalogo_commands.PresentacionModificarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0
        sin_cambios = catalogo_repository.obtener_presentacion_por_id(
            organizacion.id, referencia.id, db_session
        )
        assert sin_cambios is not None
        assert sin_cambios.activo is True

        sobre_corregido = _sobre(
            tipo="PRESENTACION_MODIFICAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "presentacion_id": str(referencia.id),
                "nombre": "Caja x6 renombrada",
                "unidades_base": referencia.unidades_base,
                "usar_en_venta": True,
                "usar_en_compra": True,
                "activo": True,
            },
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_presentacion_modificar,
            contenido_cls=catalogo_commands.PresentacionModificarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"


class TestPresentacionReferenciaCambiarContraElBus:
    def test_aceptado_deja_auditoria_y_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, _, producto_id, presentacion_simple_id = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-800"
        )
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="PRESENTACION_REFERENCIA_CAMBIAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id,
            contenido={
                "producto_id": str(producto_id),
                "presentacion_id": str(presentacion_simple_id),
            },
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_presentacion_referencia_cambiar,
            contenido_cls=catalogo_commands.PresentacionReferenciaCambiarContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=catalogo_commands.manejar_presentacion_referencia_cambiar,
            contenido_cls=catalogo_commands.PresentacionReferenciaCambiarContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado
        assert _contar_auditoria(db_session, operation_id) == 1
        referencia = catalogo_repository.obtener_referencia_de_producto(
            organizacion.id, producto_id, db_session
        )
        assert referencia is not None
        assert referencia.id == presentacion_simple_id

    def test_error_de_dominio_revierte_la_reserva_y_permite_reintentar(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, _, producto_id, presentacion_simple_id = _crear_producto_con_presentaciones(
            db_session, organizacion.id, codigo="VA-900"
        )
        referencia_original = catalogo_repository.obtener_referencia_de_producto(
            organizacion.id, producto_id, db_session
        )
        assert referencia_original is not None
        # Candidata inválida: inactiva, no puede convertirse en referencia (CAT-03).
        candidata_inactiva = catalogo_repository.crear_presentacion(
            organizacion.id,
            db_session,
            presentacion_id=nuevo_id(),
            producto_id=producto_id,
            nombre="Pack promocional",
            unidades_base=3,
            usar_en_venta=True,
            usar_en_compra=True,
            es_referencia=False,
            activo=False,
            momento=MOMENTO,
        )
        db_session.commit()

        operation_id_fallido = uuid4()
        sobre_fallido = _sobre(
            tipo="PRESENTACION_REFERENCIA_CAMBIAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "producto_id": str(producto_id),
                "presentacion_id": str(candidata_inactiva.id),
            },
        )
        with pytest.raises(ReferenciaInvalidaError):
            _procesar(
                db_session,
                sobre_fallido,
                handler=catalogo_commands.manejar_presentacion_referencia_cambiar,
                contenido_cls=catalogo_commands.PresentacionReferenciaCambiarContenidoV1,
            )

        assert _contar_auditoria(db_session, operation_id_fallido) == 0
        assert _reserva_de_comando(db_session, operation_id_fallido) == 0
        referencia_sin_cambios = catalogo_repository.obtener_referencia_de_producto(
            organizacion.id, producto_id, db_session
        )
        assert referencia_sin_cambios is not None
        assert referencia_sin_cambios.id == referencia_original.id

        sobre_corregido = _sobre(
            tipo="PRESENTACION_REFERENCIA_CAMBIAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=operation_id_fallido,
            contenido={
                "producto_id": str(producto_id),
                "presentacion_id": str(presentacion_simple_id),
            },
        )
        comando = _procesar(
            db_session,
            sobre_corregido,
            handler=catalogo_commands.manejar_presentacion_referencia_cambiar,
            contenido_cls=catalogo_commands.PresentacionReferenciaCambiarContenidoV1,
        )
        assert comando.estado == "ACEPTADO"
