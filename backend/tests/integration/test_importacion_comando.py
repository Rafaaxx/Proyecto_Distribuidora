"""Tareas 4.1 y 4.2 (change 10): `IMPORTACION_REGISTRAR` v1 por el bus, con proveedores,
contra PostgreSQL real.

Se procesa por `sync_service.procesar_comando`, que maneja la transacción (mismo
criterio que `test_stock_comandos.py`). La cobertura HTTP es de
`test_importacion_api.py`; acá se prueba el comando: catálogo, esquema estricto,
permiso, todo o nada con informe completo, idempotencia, auditoría única del bus y
la falla inyectada a mitad de archivo.

Reglas citadas: CAT-01, INV-01, INV-06, INV-21, SYN-02, SYN-06, TR-10, AUD-01,
`01` §21, ADR-022 y `design.md` D1, D6, D10, D14.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_proveedor,
    crear_usuario_y_dispositivo,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands import catalogo as catalogo_bus
from app.commands import registro
from app.commands.errores import ComandoInconsistenteError, ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import PermisoRequeridoError
from app.modules.identidad.models import Auditoria
from app.modules.importacion import commands as importacion_commands
from app.modules.importacion.domain.errores import (
    ColumnasInvalidasError,
    ImportacionConErroresError,
    TipoImportacionInvalidoError,
)
from app.modules.importacion.models import Importacion
from app.modules.proveedores import service as proveedores_service
from app.modules.proveedores.models import Proveedor
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

TIPO = "IMPORTACION_REGISTRAR"


def fila(
    numero: int,
    nombre: str,
    cuit: str = "",
    contacto: str = "",
    telefono: str = "",
    email: str = "",
) -> dict[str, Any]:
    return {
        "fila": numero,
        "valores": {
            "nombre": nombre,
            "cuit": cuit,
            "contacto": contacto,
            "telefono": telefono,
            "email": email,
        },
    }


def contenido(filas: list[dict[str, Any]], **cambios: object) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "tipo": "PROVEEDORES",
        "archivo_nombre": "proveedores.csv",
        "filas": filas,
    }
    cuerpo.update(cambios)
    return cuerpo


class Entorno:
    def __init__(
        self, sesion: Session, *, permisos: frozenset[str] = frozenset({"IMPORTAR_DATOS"})
    ) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        sesion.commit()

    def sobre(self, cuerpo: dict[str, Any], *, operation_id: UUID | None = None) -> SobreComando:
        return SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=TIPO,
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

    def proveedores(self, organizacion_id: UUID | None = None) -> list[Proveedor]:
        return list(
            self.sesion.scalars(
                select(Proveedor)
                .where(Proveedor.organizacion_id == (organizacion_id or self.org))
                .order_by(Proveedor.nombre)
            ).all()
        )

    def importaciones(self) -> list[Importacion]:
        return list(
            self.sesion.scalars(
                select(Importacion).where(Importacion.organizacion_id == self.org)
            ).all()
        )

    def comandos(self, operation_id: UUID) -> int:
        return (
            self.sesion.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.operation_id == operation_id)
            )
            or 0
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


@pytest.fixture
def entorno(db_session: Session) -> Entorno:
    return Entorno(db_session)


def _errores(error: ImportacionConErroresError) -> list[tuple[int, str | None, str]]:
    assert error.extension is not None
    return [(e["fila"], e["columna"], e["codigo"]) for e in error.extension["errores"]]


# --- catálogo y esquema ---------------------------------------------------------


def test_el_tipo_esta_declarado_online_y_sin_offline_con_handler_v1() -> None:
    """`02` §6.5: solo online."""
    declarado = catalogo_bus.tipo_declarado(TIPO)

    assert declarado is not None
    assert declarado.admite_online is True
    assert declarado.admite_offline is False
    handler = registro.resolver_handler(TIPO, 1)
    assert (handler.tipo, handler.version) == (TIPO, 1)


@pytest.mark.parametrize(
    "cambios",
    [
        {"organizacion_id": str(uuid4())},
        {"estado": "CONFIRMADA"},
        {"archivo_nombre": None},
        {"filas": "no-es-una-lista"},
        {"filas": [{"fila": "dos", "valores": {}}]},
        {"filas": [{"fila": 2, "valores": {"nombre": 5}}]},
        {"filas": [{"fila": 2, "valores": {"nombre": "A"}, "extra": 1}]},
    ],
)
def test_un_contenido_malformado_se_rechaza_sin_efectos(
    entorno: Entorno, cambios: dict[str, object]
) -> None:
    """SYN-06: `extra="forbid"`: la organización sale del token, no del contenido."""
    cuerpo = contenido([fila(2, "Bodega Sur")])
    cuerpo.update(cambios)

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(cuerpo)

    assert entorno.proveedores() == []
    assert entorno.importaciones() == []


@pytest.mark.parametrize("faltante", ["tipo", "archivo_nombre", "filas"])
def test_un_campo_obligatorio_faltante_se_rechaza(entorno: Entorno, faltante: str) -> None:
    cuerpo = contenido([fila(2, "Bodega Sur")])
    del cuerpo[faltante]

    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(cuerpo)


@pytest.mark.parametrize("tipo", ["PRECIOS", "VENTAS", "proveedores", ""])
def test_un_tipo_sin_importador_se_rechaza_sin_efectos(entorno: Entorno, tipo: str) -> None:
    """D9: `PRECIOS` no tiene importador hasta el change 13."""
    operation_id = uuid4()

    with pytest.raises(TipoImportacionInvalidoError):
        entorno.enviar(contenido([fila(2, "Bodega Sur")], tipo=tipo), operation_id=operation_id)

    assert entorno.proveedores() == []
    assert entorno.comandos(operation_id) == 0


def test_las_columnas_de_las_filas_deben_ser_las_del_tipo(entorno: Entorno) -> None:
    """El contenido no admite una columna de más (p. ej. `organizacion_id`)."""
    sucia = fila(2, "Bodega Sur")
    sucia["valores"]["organizacion_id"] = str(uuid4())

    with pytest.raises(ColumnasInvalidasError):
        entorno.enviar(contenido([sucia]))

    assert entorno.proveedores() == []


def test_un_archivo_sin_filas_se_rechaza(entorno: Entorno) -> None:
    with pytest.raises(ContenidoDeComandoInvalidoError):
        entorno.enviar(contenido([]))


# --- alta exitosa (4.1) -------------------------------------------------------------


def test_dos_filas_validas_crean_dos_proveedores_y_una_fila_de_importacion(
    entorno: Entorno,
) -> None:
    """Escenario "Importación aceptada" y "Dos proveedores válidos": existen los dos
    proveedores activos, el CUIT normalizado a 11 dígitos, una fila en `importacion`
    con el estado de éxito y UNA sola auditoría del comando (AUD-01, ADR-022)."""
    operation_id = uuid4()

    comando = entorno.enviar(
        contenido(
            [fila(2, "Bodega Sur", "30-71234567-8", contacto="Ana"), fila(3, "Cervecería Norte")]
        ),
        operation_id=operation_id,
    )

    assert comando.estado == "ACEPTADO"
    bodega, cerveceria = entorno.proveedores()
    assert (bodega.nombre, bodega.cuit, bodega.activo, bodega.contacto) == (
        "Bodega Sur",
        "30712345678",
        True,
        "Ana",
    )
    assert (cerveceria.nombre, cerveceria.cuit, cerveceria.activo) == (
        "Cervecería Norte",
        None,
        True,
    )
    assert bodega.actualizado_por_id == entorno.usuario_id

    (importacion,) = entorno.importaciones()
    assert importacion.tipo == "PROVEEDORES"
    assert importacion.archivo_nombre == "proveedores.csv"
    assert importacion.estado == "CONFIRMADA"
    assert (importacion.filas_total, importacion.filas_ok, importacion.filas_error) == (2, 2, 0)
    assert importacion.errores == []
    assert importacion.operation_id == operation_id
    assert importacion.usuario_id == entorno.usuario_id
    assert importacion.dispositivo_id == entorno.dispositivo_id
    assert importacion.occurred_at == MOMENTO
    assert comando.resultado == {
        "importacion_id": str(importacion.id),
        "filas_total": 2,
        "filas_ok": 2,
    }
    assert entorno.auditorias(operation_id) == 1


def test_una_sola_fila_tambien_se_importa(entorno: Entorno) -> None:
    comando = entorno.enviar(contenido([fila(2, "Bodega Sur")], archivo_nombre="otro.xlsx"))

    assert [p.nombre for p in entorno.proveedores()] == ["Bodega Sur"]
    (importacion,) = entorno.importaciones()
    assert importacion.archivo_nombre == "otro.xlsx"
    assert comando.resultado is not None
    assert comando.resultado["filas_total"] == 1


def test_inv21_los_proveedores_se_crean_en_la_organizacion_del_sobre(
    entorno: Entorno, db_session: Session
) -> None:
    otra = crear_organizacion(db_session).id
    db_session.commit()

    entorno.enviar(contenido([fila(2, "Bodega Sur")]))

    assert len(entorno.proveedores()) == 1
    assert entorno.proveedores(otra) == []


# --- todo o nada con informe completo (4.1) ---------------------------------------


def test_una_fila_con_cuit_invalido_y_otra_con_nombre_duplicado_dan_los_dos_errores(
    entorno: Entorno,
) -> None:
    """Escenario "Una fila mala impide toda la importación": 422
    `IMPORTACION_CON_ERRORES` con los DOS errores y ningún proveedor nuevo."""
    crear_proveedor(entorno.sesion, entorno.org, nombre="Bodega Sur")
    entorno.sesion.commit()
    operation_id = uuid4()

    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(
            contenido(
                [
                    fila(2, "Cervecería Norte"),  # válida: no debe quedar creada
                    fila(3, "Distribuidora Este", "20-1234"),
                    fila(4, "Bodega Sur"),
                ]
            ),
            operation_id=operation_id,
        )

    assert error.value.status_http == 422
    assert error.value.codigo == "IMPORTACION_CON_ERRORES"
    assert _errores(error.value) == [
        (3, "cuit", "CUIT_INVALIDO"),
        (4, "nombre", "NOMBRE_DUPLICADO"),
    ]
    assert [p.nombre for p in entorno.proveedores()] == ["Bodega Sur"]  # solo el previo
    assert entorno.importaciones() == []
    assert entorno.comandos(operation_id) == 0  # la reserva del `operation_id` se revierte
    assert entorno.auditorias(operation_id) == 0


def test_el_error_de_fila_trae_el_mismo_codigo_y_mensaje_que_el_alta_individual(
    entorno: Entorno,
) -> None:
    """TR-10: `CUIT_INVALIDO` en la fila 2, columna `cuit`."""
    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(contenido([fila(2, "Bodega Sur", "20-1234")]))

    assert error.value.extension is not None
    (reporte,) = error.value.extension["errores"]
    assert reporte["fila"] == 2
    assert reporte["columna"] == "cuit"
    assert reporte["codigo"] == "CUIT_INVALIDO"
    assert "11 dígitos" in reporte["mensaje"]


def test_el_nombre_vacio_y_el_cuit_repetido_con_uno_existente_se_informan_por_fila(
    entorno: Entorno,
) -> None:
    proveedores_service.crear_proveedor(
        entorno.org,
        entorno.sesion,
        RELOJ,
        nombre="Existente",
        cuit="30712345678",
        contacto=None,
        telefono=None,
        email=None,
        actor_id=entorno.usuario_id,
    )
    entorno.sesion.commit()

    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(contenido([fila(2, ""), fila(3, "Otro", "30-71234567-8"), fila(4, "Bueno")]))

    assert _errores(error.value) == [
        (2, "nombre", "NOMBRE_INVALIDO"),
        (3, "cuit", "CUIT_DUPLICADO"),
    ]
    assert [p.nombre for p in entorno.proveedores()] == ["Existente"]


def test_una_fila_repetida_dentro_del_archivo_da_fila_duplicada_y_no_crea_nada(
    entorno: Entorno,
) -> None:
    """Escenario "Clave repetida dentro del archivo": "Bodega Sur" en las filas 2 y
    5; la fila 5 da `FILA_DUPLICADA` citando la fila 2."""
    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(
            contenido(
                [
                    fila(2, "Bodega Sur"),
                    fila(3, "Norte"),
                    fila(4, "Este"),
                    fila(5, "bodega sur"),
                ]
            )
        )

    assert _errores(error.value) == [(5, "nombre", "FILA_DUPLICADA")]
    assert error.value.extension is not None
    assert "2" in error.value.extension["errores"][0]["mensaje"]
    assert entorno.proveedores() == []
    assert entorno.importaciones() == []


def test_el_cuit_repetido_dentro_del_archivo_da_fila_duplicada_en_la_columna_cuit(
    entorno: Entorno,
) -> None:
    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(
            contenido([fila(2, "A", "30712345678"), fila(3, "B", "30-71234567-8"), fila(4, "C")])
        )

    assert _errores(error.value) == [(3, "cuit", "FILA_DUPLICADA")]
    assert entorno.proveedores() == []


def test_todos_los_errores_se_informan_ordenados_por_fila_aunque_sean_de_distinto_origen(
    entorno: Entorno,
) -> None:
    crear_proveedor(entorno.sesion, entorno.org, nombre="Existente")
    entorno.sesion.commit()

    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(
            contenido(
                [
                    fila(2, "Nuevo"),
                    fila(3, "Existente"),  # NOMBRE_DUPLICADO
                    fila(4, "Nuevo"),  # FILA_DUPLICADA (de la 2)
                    fila(5, "X", "1"),  # CUIT_INVALIDO
                ]
            )
        )

    assert _errores(error.value) == [
        (3, "nombre", "NOMBRE_DUPLICADO"),
        (4, "nombre", "FILA_DUPLICADA"),
        (5, "cuit", "CUIT_INVALIDO"),
    ]
    assert [p.nombre for p in entorno.proveedores()] == ["Existente"]


def test_corregir_y_reenviar_importa_todo_sin_duplicar_nada_de_la_primera_tentativa(
    entorno: Entorno,
) -> None:
    """Escenario "Corregir y reenviar": la tentativa rechazada no dejó efectos, así
    que el archivo corregido se importa entero con un `operation_id` nuevo."""
    with pytest.raises(ImportacionConErroresError):
        entorno.enviar(contenido([fila(2, "Bodega Sur"), fila(3, "Norte", "20-1234")]))

    comando = entorno.enviar(contenido([fila(2, "Bodega Sur"), fila(3, "Norte", "20123456786")]))

    assert comando.estado == "ACEPTADO"
    assert [p.nombre for p in entorno.proveedores()] == ["Bodega Sur", "Norte"]
    assert len(entorno.importaciones()) == 1


# --- idempotencia (INV-06) ------------------------------------------------------------


def test_el_doble_envio_con_el_mismo_operation_id_devuelve_el_resultado_original(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío" (INV-06, SYN-02)."""
    operation_id = uuid4()
    cuerpo = contenido([fila(2, "Bodega Sur"), fila(3, "Norte")])

    primero = entorno.enviar(cuerpo, operation_id=operation_id)
    segundo = entorno.enviar(cuerpo, operation_id=operation_id)

    assert primero.resultado == segundo.resultado
    assert len(entorno.proveedores()) == 2
    assert len(entorno.importaciones()) == 1
    assert entorno.auditorias(operation_id) == 1


def test_el_mismo_operation_id_con_otro_archivo_es_comando_inconsistente(
    entorno: Entorno,
) -> None:
    """Escenario "Mismo Operation-Id con otro archivo" (SYN-02)."""
    operation_id = uuid4()
    entorno.enviar(contenido([fila(2, "Bodega Sur")]), operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.enviar(contenido([fila(2, "Otra Bodega")]), operation_id=operation_id)

    assert [p.nombre for p in entorno.proveedores()] == ["Bodega Sur"]
    assert len(entorno.importaciones()) == 1


def test_el_mismo_archivo_con_otro_operation_id_choca_con_lo_ya_importado(
    entorno: Entorno,
) -> None:
    """D6: archivo importado dos veces por error con distinto `Operation-Id`: el
    segundo falla entero por duplicados, no duplica."""
    cuerpo = contenido([fila(2, "Bodega Sur")])
    entorno.enviar(cuerpo)

    with pytest.raises(ImportacionConErroresError) as error:
        entorno.enviar(cuerpo)

    assert _errores(error.value) == [(2, "nombre", "NOMBRE_DUPLICADO")]
    assert len(entorno.proveedores()) == 1


# --- permiso y modo offline ------------------------------------------------------------


def test_sin_importar_datos_se_rechaza_sin_efectos_ni_reserva(db_session: Session) -> None:
    """Escenario "Sin permiso": `GESTIONAR_PROVEEDORES` no alcanza; 403 y nada escrito."""
    entorno = Entorno(db_session, permisos=frozenset({"GESTIONAR_PROVEEDORES"}))
    operation_id = uuid4()

    with pytest.raises(PermisoRequeridoError) as error:
        entorno.enviar(contenido([fila(2, "Bodega Sur")]), operation_id=operation_id)

    assert error.value.status_http == 403
    assert entorno.proveedores() == []
    assert entorno.importaciones() == []
    assert entorno.comandos(operation_id) == 0


def test_el_lote_rechaza_la_importacion_enviada_sin_conexion(entorno: Entorno) -> None:
    """Escenario "Modo offline rechazado" (`02` §6.5): el bus real, no solo el
    catálogo, la rechaza con un código estable y sin efectos."""
    operation_id = uuid4()
    item = ItemLote(
        operation_id=operation_id,
        tipo=TIPO,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido([fila(2, "Bodega Sur")]),
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.proveedores() == []
    assert entorno.comandos(operation_id) == 0


# --- INV-01: falla inyectada a mitad de archivo (4.2) -------------------------------------


def test_inv01_una_falla_inyectada_despues_de_escribir_la_fila_5_de_10_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escenario "Falla inyectada a mitad de archivo": ninguna fila escrita, ni la
    fila de `importacion`, ni la reserva, ni la auditoría (INV-01, `02` §15)."""
    original = proveedores_service.crear_proveedor
    escritas: list[str] = []

    def con_falla(*args: Any, **kwargs: Any) -> Proveedor:
        if len(escritas) == 5:
            raise RuntimeError("falla inyectada después de escribir la fila 5")
        proveedor = original(*args, **kwargs)
        escritas.append(proveedor.nombre)
        return proveedor

    monkeypatch.setattr(proveedores_service, "crear_proveedor", con_falla)
    operation_id = uuid4()
    filas = [fila(numero, f"Proveedor {numero}") for numero in range(2, 12)]

    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.enviar(contenido(filas), operation_id=operation_id)

    assert len(escritas) == 5  # la falla ocurrió con cinco filas ya escritas
    entorno.sesion.rollback()
    assert entorno.proveedores() == []
    assert entorno.importaciones() == []
    assert entorno.comandos(operation_id) == 0
    assert entorno.auditorias(operation_id) == 0


def test_inv01_una_falla_al_registrar_la_importacion_revierte_los_proveedores(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La última escritura (la fila de `importacion`) también es parte de la misma
    transacción: si falla, no queda ningún proveedor."""
    from app.modules.importacion import repository

    def falla(*args: Any, **kwargs: Any) -> Importacion:
        raise RuntimeError("falla al registrar la importación")

    monkeypatch.setattr(repository, "crear_importacion", falla)

    with pytest.raises(RuntimeError, match="falla al registrar"):
        entorno.enviar(contenido([fila(2, "Bodega Sur"), fila(3, "Norte")]))

    entorno.sesion.rollback()
    assert entorno.proveedores() == []
    assert entorno.importaciones() == []
