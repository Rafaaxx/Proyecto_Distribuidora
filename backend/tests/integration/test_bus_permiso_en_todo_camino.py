"""Change 18b, tarea 22.3 (`design.md` D23, ADR-056; spec `sistema/pipeline-de-comandos`, requisito
"El permiso del tipo se exige en todo camino"): el paso 4 de `02` §6.3 vive en `procesar_comando`,
no en cada ruta ni en cada handler. Por el lote en modo `ONLINE`, un usuario sin ninguno de los
permisos del catálogo recibe `PERMISO_REQUERIDO` antes del handler, sin fila de `comando` ni efecto.

Reglas citadas: SEG-06, ADR-028, ADR-056, INV-01, SYN-10.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import crear_organizacion, crear_usuario_y_dispositivo
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from stock_utiles import crear_jornada_sql, crear_ubicacion_sql

import app.main  # noqa: F401  (registra todos los handlers de producción)
from app.commands import catalogo, registro
from app.commands.catalogo import OperacionObservable
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Dispositivo, IntentoLogin
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando, Observacion
from app.modules.sync.service import ItemLote

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

_CATALOGO_REAL = dict(catalogo._CATALOGO)
TIPOS_PARAMETRIZADOS = sorted(
    t.tipo for t in _CATALOGO_REAL.values() if not t.exige_credenciales_efimeras
)
TIPOS_CON_SECRETOS = sorted(
    t.tipo for t in _CATALOGO_REAL.values() if t.exige_credenciales_efimeras
)


class Entorno:
    def __init__(self, sesion: Session, *, permisos: frozenset[str] = frozenset()) -> None:
        self.sesion = sesion
        self.org = crear_organizacion(sesion).id
        self.usuario_id, self.dispositivo_id = crear_usuario_y_dispositivo(
            sesion, self.org, permisos=permisos
        )
        sesion.commit()

    def item(
        self,
        tipo: str,
        contenido: dict[str, object],
        *,
        version: int = 1,
        modo: str = "ONLINE",
        operation_id: UUID | None = None,
        jornada_id: UUID | None = None,
    ) -> ItemLote:
        return ItemLote(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=version,
            modo=modo,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,  # type: ignore[arg-type]
            jornada_id=jornada_id,
        )

    def lote(self, item: ItemLote) -> sync_service.ResultadoItemLote:
        (resultado,) = sync_service.procesar_lote(
            self.sesion,
            RELOJ,
            organizacion_id=self.org,
            usuario_id=self.usuario_id,
            dispositivo_id=self.dispositivo_id,
            items=[item],
        )
        return resultado

    def comandos(self, operation_id: UUID) -> int:
        self.sesion.rollback()
        return int(
            self.sesion.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.organizacion_id == self.org, Comando.operation_id == operation_id)
            )
            or 0
        )


def _version_del_tipo(tipo: str) -> int:
    versiones = [v for (t, v) in registro._REGISTRO if t == tipo]
    return max(versiones)


@pytest.mark.parametrize("tipo", TIPOS_PARAMETRIZADOS)
def test_seg06_un_usuario_sin_los_permisos_del_tipo_recibe_permiso_requerido_por_el_lote(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tipo: str
) -> None:
    """Parametrizada sobre TODO el catálogo: cualquiera sea el tipo, el lote en `ONLINE` rechaza a
    quien no tiene ninguno de sus permisos, sin fila de `comando`. El contenido no se valida
    contra el esquema real (el paso 4 no depende de él): se cambia la validación por una
    identidad para no fabricar un contenido válido de cada uno de los 62 tipos."""
    monkeypatch.setattr(registro, "validar_contenido", lambda _handler, contenido: contenido)
    entorno = Entorno(db_session)
    item = entorno.item(tipo, {}, version=_version_del_tipo(tipo))

    resultado = entorno.lote(item)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert entorno.comandos(item.operation_id) == 0


@pytest.mark.parametrize("tipo", TIPOS_CON_SECRETOS)
def test_syn06_los_tipos_con_secretos_no_entran_por_el_lote_aunque_se_tenga_el_permiso(
    db_session: Session, tipo: str
) -> None:
    permisos = frozenset(_CATALOGO_REAL[tipo].permisos)
    entorno = Entorno(db_session, permisos=permisos)
    item = entorno.item(tipo, {}, version=_version_del_tipo(tipo))

    resultado = entorno.lote(item)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.comandos(item.operation_id) == 0


def test_seg06_rol_permisos_cambiar_sin_permiso_no_cambia_el_rol(db_session: Session) -> None:
    """El caso más grave: quien no administra usuarios no puede darse permisos por el lote."""
    entorno = Entorno(db_session, permisos=frozenset({"VENDER"}))
    rol_id = db_session.scalar(
        text("SELECT rol_id FROM usuario WHERE id = :u"), {"u": entorno.usuario_id}
    )
    item = entorno.item(
        "ROL_PERMISOS_CAMBIAR", {"rol_id": str(rol_id), "permisos": ["VENDER", "ADMIN_USUARIOS"]}
    )

    resultado = entorno.lote(item)

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
    assert entorno.comandos(item.operation_id) == 0
    assert identidad_repository.listar_permisos_de_rol(entorno.org, rol_id, db_session) == [
        "VENDER"
    ]


def test_seg06_usuario_desbloquear_sin_permiso_no_deja_el_marcador(db_session: Session) -> None:
    entorno = Entorno(db_session)
    item = entorno.item("USUARIO_DESBLOQUEAR", {"usuario_id": str(entorno.usuario_id)})

    resultado = entorno.lote(item)

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
    marcadores = db_session.scalar(
        select(func.count())
        .select_from(IntentoLogin)
        .where(IntentoLogin.usuario_id == entorno.usuario_id, IntentoLogin.exito.is_(True))
    )
    assert marcadores == 0


def test_seg06_dispositivo_revocar_sin_permiso_no_revoca_el_dispositivo(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session)
    _otro_usuario, otro_dispositivo = crear_usuario_y_dispositivo(db_session, entorno.org)
    db_session.commit()
    item = entorno.item("DISPOSITIVO_REVOCAR", {"dispositivo_id": str(otro_dispositivo)})

    resultado = entorno.lote(item)

    assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
    estado = db_session.scalar(select(Dispositivo.estado).where(Dispositivo.id == otro_dispositivo))
    assert estado == "ACTIVO"


def test_seg06_producto_modificar_y_costo_informar_sin_permiso_no_dejan_comando(
    db_session: Session,
) -> None:
    """Contenido VÁLIDO contra el esquema real (sin parche): la denegación no depende de él."""
    entorno = Entorno(db_session)
    producto = entorno.item(
        "PRODUCTO_MODIFICAR",
        {
            "producto_id": str(uuid4()),
            "codigo": "X1",
            "nombre": "Vino",
            "categoria_id": str(uuid4()),
            "proveedor_id": str(uuid4()),
            "unidad_base": "UNIDAD",
            "alicuota_id": str(uuid4()),
            "activo": True,
        },
        version=2,
    )
    costo = entorno.item(
        "COSTO_INFORMAR",
        {
            "proveedor_id": str(uuid4()),
            "costos": [
                {
                    "producto_id": str(uuid4()),
                    "presentacion_id": str(uuid4()),
                    "valor": "100.00",
                    "incluye_iva": False,
                    "vigencia_desde": "2026-10-01",
                }
            ],
        },
    )

    for item in (producto, costo):
        resultado = entorno.lote(item)
        assert (resultado.estado, resultado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
        assert entorno.comandos(item.operation_id) == 0


def test_seg06_con_el_permiso_el_lote_da_el_mismo_resultado_que_la_via_rest(
    db_session: Session,
) -> None:
    """Triangulación: con el permiso del catálogo, el mismo comando por el lote y por el camino
    que usa cada `api.py` (`procesar_comando` con el handler registrado) termina igual."""
    entorno = Entorno(db_session, permisos=frozenset({"GESTIONAR_DISPOSITIVOS"}))
    _usuario_a, dispositivo_a = crear_usuario_y_dispositivo(db_session, entorno.org)
    _usuario_b, dispositivo_b = crear_usuario_y_dispositivo(db_session, entorno.org)
    db_session.commit()

    por_lote = entorno.lote(
        entorno.item("DISPOSITIVO_REVOCAR", {"dispositivo_id": str(dispositivo_a)})
    )

    sobre = SobreComando(
        operation_id=uuid4(),
        tipo="DISPOSITIVO_REVOCAR",
        version=1,
        modo="ONLINE",
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"dispositivo_id": str(dispositivo_b)},
    )
    registrado = registro.resolver_handler(sobre.tipo, 1)
    validado = registro.validar_contenido(registrado, sobre.contenido)
    por_rest = sync_service.procesar_comando(
        db_session,
        RELOJ,
        sobre=sobre,
        huella="h",
        ejecutar_handler=lambda sesion: registrado.funcion(  # type: ignore[return-value]
            sobre, validado, sesion=sesion, reloj=RELOJ
        ),
    )

    assert por_lote.estado == por_rest.estado == "ACEPTADO"
    assert por_lote.resultado is not None and por_rest.resultado is not None
    assert por_lote.resultado["estado"] == por_rest.resultado["estado"] == "REVOCADO"


# --- usuario inactivo con token vigente: ONLINE -> PERMISO_REQUERIDO, OFFLINE -> PERMISO_REVOCADO


class _Esquema(BaseModel):
    pass


def _handler_de_prueba(
    sobre: SobreComando, contenido: _Esquema, *, sesion: object, reloj: object
) -> tuple[str, dict[str, object] | None, str | None]:
    return "ACEPTADO", {"operacion_id": str(sobre.operation_id)}, None


TIPO_DE_PRUEBA = "PRUEBA_PERMISO_EN_TODO_CAMINO"


@pytest.fixture
def _tipo_de_prueba(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo(
        TIPO_DE_PRUEBA,
        admite_online=True,
        admite_offline=True,
        permisos=("REGISTRAR_COBRANZA",),
        operacion_offline=OperacionObservable("OPERACION_DE_PRUEBA", "operacion_id"),
    )
    registro.registrar_handler(TIPO_DE_PRUEBA, 1, _Esquema)(_handler_de_prueba)


@pytest.mark.usefixtures("_tipo_de_prueba")
def test_seg06_un_usuario_inactivo_recibe_permiso_requerido_online_y_permiso_revocado_offline(
    db_session: Session,
) -> None:
    entorno = Entorno(db_session, permisos=frozenset({"REGISTRAR_COBRANZA"}))
    db_session.execute(
        text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u"), {"u": entorno.usuario_id}
    )
    db_session.commit()

    jornada_id = crear_jornada_sql(
        db_session,
        entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        ubicacion_id=crear_ubicacion_sql(db_session, entorno.org, requiere_toma=True),
    )
    db_session.commit()
    online = entorno.item(TIPO_DE_PRUEBA, {}, jornada_id=jornada_id)
    resultado_online = entorno.lote(online)
    offline = entorno.item(TIPO_DE_PRUEBA, {}, modo="OFFLINE", jornada_id=jornada_id)
    resultado_offline = entorno.lote(offline)

    assert (resultado_online.estado, resultado_online.error_codigo) == (
        "RECHAZADO",
        "PERMISO_REQUERIDO",
    )
    assert entorno.comandos(online.operation_id) == 0
    assert resultado_offline.estado == "ACEPTADO_CON_OBSERVACIONES"
    comando = db_session.scalar(
        select(Comando).where(
            Comando.organizacion_id == entorno.org, Comando.operation_id == offline.operation_id
        )
    )
    assert comando is not None
    (observacion,) = db_session.scalars(
        select(Observacion).where(Observacion.comando_id == comando.id)
    ).all()
    assert observacion.codigo == "PERMISO_REVOCADO"
    assert observacion.detalle["motivo"] == "USUARIO_INACTIVO"


@pytest.mark.usefixtures("_tipo_de_prueba")
def test_seg06_con_uno_cualquiera_de_los_permisos_del_tipo_alcanza(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un tipo con varios permisos (`PIN_AUTORIZACION_PROPIO_DEFINIR`): alcanza con uno."""
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    catalogo.declarar_tipo(
        TIPO_DE_PRUEBA,
        admite_online=True,
        admite_offline=False,
        permisos=("VENDER", "ANULAR_VENTA"),
    )
    con_segundo = Entorno(db_session, permisos=frozenset({"ANULAR_VENTA"}))
    sin_ninguno = Entorno(db_session, permisos=frozenset({"EDITAR_COSTOS"}))

    aceptado = con_segundo.lote(con_segundo.item(TIPO_DE_PRUEBA, {}))
    rechazado = sin_ninguno.lote(sin_ninguno.item(TIPO_DE_PRUEBA, {}))

    assert aceptado.estado == "ACEPTADO"
    assert (rechazado.estado, rechazado.error_codigo) == ("RECHAZADO", "PERMISO_REQUERIDO")
