"""Lote de sincronización (change 04, grupo 8, tareas 8.1-8.6, 8.10;
`docs/02-arquitectura.md` §6.4, spec `sync/lote-de-comandos`).

Combina pruebas a nivel de servicio (`sync_service.procesar_lote`, con
`db_session`, mismo criterio que `test_bus_transaccion.py` del grupo 6) y a
nivel de HTTP (`POST /api/v1/sync/comandos`, con login real, mismo patrón
que `test_bus_entrada_rest.py` del grupo 7 y el ratchet de aislamiento
INV-21: nunca un access token fabricado a mano).

Un único tipo de comando de prueba ("PRUEBA_LOTE") se registra en el
catálogo y en el registro de handlers, aislado por `monkeypatch` (mismo
patrón que `test_commands_catalogo.py`/`test_commands_registro.py`): su
contenido declara qué debe devolver el handler (`resultado`:
"ACEPTADO"/"RECHAZADO"/"TRANSITORIO"), para poder ejercer los cuatro
caminos del lote (8.1-8.4) con un solo tipo. Un segundo tipo
("PRUEBA_LOTE_SOLO_ONLINE") declarado sin `admite_offline` cubre la tarea
8.10.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.commands import catalogo, registro
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Organizacion
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-de-prueba-lote-123"
JWT_SECRET = "secreto-de-prueba-lote-sincronizacion"


class _EsquemaPrueba(BaseModel):
    resultado: Literal["ACEPTADO", "RECHAZADO", "TRANSITORIO"] = "ACEPTADO"
    etiqueta: str | None = None


class _ErrorTransitorioSimulado(Exception):
    """Simula un `DBAPIError` con `.orig.sqlstate = "40001"` (serialización,
    `02` §6.3): `es_error_transitorio` (`sync/service.py`, grupo 6) solo mira
    ese atributo, así que no hace falta provocar un conflicto real de
    PostgreSQL para probar la ORQUESTACIÓN del lote (tarea 8.4) -- el
    mecanismo de detección ya tiene su propia prueba con PostgreSQL real en
    `test_bus_transaccion.py::TestReintentosTransitoriosConBaseReal`
    (grupo 6)."""

    class _Orig:
        sqlstate = "40001"

    def __init__(self) -> None:
        super().__init__("error transitorio simulado")
        self.orig = self._Orig()


def _handler_prueba(
    sobre: SobreComando, contenido: _EsquemaPrueba
) -> tuple[str, dict[str, object] | None, str | None]:
    if contenido.resultado == "RECHAZADO":
        return "RECHAZADO", None, "RECHAZADO_DE_PRUEBA"
    if contenido.resultado == "TRANSITORIO":
        raise _ErrorTransitorioSimulado()
    return "ACEPTADO", {"etiqueta": contenido.etiqueta}, None


@pytest.fixture(autouse=True)
def _catalogo_y_registro_aislados(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.commands.catalogo._CATALOGO", {})
    monkeypatch.setattr("app.commands.registro._REGISTRO", {})
    catalogo.declarar_tipo("PRUEBA_LOTE", admite_online=True, admite_offline=True)
    registro.registrar_handler("PRUEBA_LOTE", 1, _EsquemaPrueba)(_handler_prueba)
    catalogo.declarar_tipo("PRUEBA_LOTE_SOLO_ONLINE", admite_online=True, admite_offline=False)
    registro.registrar_handler("PRUEBA_LOTE_SOLO_ONLINE", 1, _EsquemaPrueba)(_handler_prueba)


def _crear_organizacion(sesion: Session, *, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba lote",
        slug=slug,
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


def _crear_usuario_y_dispositivo(
    sesion: Session, organizacion_id: UUID, *, nombre_usuario: str | None = None
) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Vendedor",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=nombre_usuario or f"vendedor-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"P{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _item(
    *,
    usuario_id: UUID,
    dispositivo_id: UUID,
    secuencia: int,
    resultado: str = "ACEPTADO",
    tipo: str = "PRUEBA_LOTE",
    modo: str = "ONLINE",
    operation_id: UUID | None = None,
    etiqueta: str | None = None,
) -> ItemLote:
    return ItemLote(
        operation_id=operation_id or uuid4(),
        tipo=tipo,
        version=1,
        modo=modo,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=secuencia,
        app_version="1.0.0",
        contenido={"resultado": resultado, "etiqueta": etiqueta or f"seq-{secuencia}"},
    )


# --- Nivel de servicio (`procesar_lote`, `db_session`) ---------------------


class TestOrdenDelLote:
    """Tarea 8.1, escenarios "Los comandos se procesan en el orden de la
    cola" y "Un lote desordenado se procesa por secuencia, no por
    posición"."""

    def test_una_venta_se_procesa_antes_que_su_anulacion(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-orden-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        venta = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1, etiqueta="venta")
        anulacion = _item(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=2, etiqueta="anulacion"
        )

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[venta, anulacion],
        )

        assert [r.resultado["etiqueta"] for r in resultados] == ["venta", "anulacion"]

    def test_un_lote_desordenado_se_procesa_por_secuencia_no_por_posicion(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-desorden-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        # Llegan en el orden 3, 1, 2 dentro de la lista, pero sus secuencias
        # son 1, 2, 3: el resultado debe reflejar el orden de SECUENCIA.
        tercero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=3, etiqueta="c")
        primero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1, etiqueta="a")
        segundo = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=2, etiqueta="b")

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[tercero, primero, segundo],
        )

        assert [r.resultado["etiqueta"] for r in resultados] == ["a", "b", "c"]


class TestTamanoDelLote:
    """Tarea 8.2, escenarios "Un lote que excede el máximo se rechaza
    entero" y "Un lote vacío no es un error". El máximo (50) se hace
    cumplir en el esquema Pydantic (`schemas.py`, tarea 8.6): acá se
    verifica el caso "lote vacío" a nivel de servicio, y el de 51 a nivel
    HTTP (más abajo, `TestEndpointHttp`), donde el 422 de Pydantic es
    observable."""

    def test_un_lote_vacio_no_es_un_error(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-vacio-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[],
        )

        assert resultados == []


class TestUnRechazoNoDetieneElLote:
    """Tarea 8.3, escenarios "Un rechazo no detiene el lote" y "Cada
    resultado se identifica por su comando"."""

    def test_el_segundo_se_rechaza_y_el_tercero_se_procesa(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-rechazo-lote-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        primero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1)
        segundo = _item(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=2, resultado="RECHAZADO"
        )
        tercero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=3)

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[primero, segundo, tercero],
        )

        assert len(resultados) == 3
        assert resultados[0].estado == "ACEPTADO"
        assert resultados[1].estado == "RECHAZADO"
        assert resultados[1].error_codigo == "RECHAZADO_DE_PRUEBA"
        assert resultados[2].estado == "ACEPTADO"

    def test_cada_resultado_se_identifica_por_su_operation_id(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-ids-lote-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        items = [
            _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=i) for i in range(1, 4)
        ]

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=items,
        )

        operation_ids_esperados = {item.operation_id for item in items}
        operation_ids_de_resultados = {r.operation_id for r in resultados}
        assert operation_ids_de_resultados == operation_ids_esperados


class TestErrorTransitorioCortaElLote:
    """Tarea 8.4, escenarios "Los comandos posteriores a un error
    transitorio no se procesan" y "El reenvío del lote cortado no duplica
    lo ya aceptado"."""

    def test_el_tercero_no_se_procesa_tras_un_error_transitorio_en_el_segundo(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-transitorio-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        primero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1)
        segundo = _item(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=2, resultado="TRANSITORIO"
        )
        tercero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=3)

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[primero, segundo, tercero],
            config=sync_service.ConfiguracionReintentos(intentos_maximos=1),
        )

        assert len(resultados) == 2
        assert resultados[0].estado == "ACEPTADO"
        assert resultados[1].estado == "ERROR_TRANSITORIO"
        assert resultados[1].error_codigo == "ERROR_TRANSITORIO"
        operation_ids = {r.operation_id for r in resultados}
        assert tercero.operation_id not in operation_ids

    def test_el_reenvio_del_lote_cortado_no_duplica_lo_ya_aceptado(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-reenvio-lote-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        primero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=1)
        # El segundo se reenvía con la MISMA huella pero un resultado
        # "ACEPTADO" en su segunda pasada (simula que la conexión se
        # recuperó): igual `operation_id`, igual `contenido`.
        segundo_original = _item(
            usuario_id=usuario, dispositivo_id=dispositivo, secuencia=2, resultado="TRANSITORIO"
        )
        tercero = _item(usuario_id=usuario, dispositivo_id=dispositivo, secuencia=3)

        primer_envio = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[primero, segundo_original, tercero],
            config=sync_service.ConfiguracionReintentos(intentos_maximos=1),
        )
        assert len(primer_envio) == 2  # cortado en el segundo

        reenvio = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[primero, segundo_original, tercero],
            config=sync_service.ConfiguracionReintentos(intentos_maximos=1),
        )

        # El primero no vuelve a ejecutarse (sigue aceptado, un solo
        # registro en `comando`); el segundo (todavía transitorio) corta de
        # nuevo; el tercero sigue sin procesarse.
        assert len(reenvio) == 2
        assert reenvio[0].operation_id == primero.operation_id
        assert reenvio[0].estado == "ACEPTADO"
        assert reenvio[1].operation_id == segundo_original.operation_id
        assert reenvio[1].estado == "ERROR_TRANSITORIO"

        total_comandos_del_primero = db_session.scalar(
            _contar_por_operation_id(primero.operation_id)
        )
        assert total_comandos_del_primero == 1


def _contar_por_operation_id(operation_id: UUID):
    from sqlalchemy import func, select

    return select(func.count()).select_from(Comando).where(Comando.operation_id == operation_id)


class TestModoNoAdmitidoParaTipoEnElLote:
    """Tarea 8.10, escenario "Un tipo que no admite offline se rechaza en
    el lote"."""

    def test_un_tipo_solo_online_se_rechaza_si_llega_offline(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-modo-lote-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        item_offline = _item(
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            secuencia=1,
            tipo="PRUEBA_LOTE_SOLO_ONLINE",
            modo="OFFLINE",
        )

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item_offline],
        )

        assert resultados[0].estado == "RECHAZADO"
        assert resultados[0].error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"

    def test_el_mismo_tipo_en_modo_online_se_acepta(self, db_session: Session) -> None:
        """Triangulación: el mismo tipo, en el modo que sí admite, se
        procesa normalmente."""
        organizacion = _crear_organizacion(db_session, slug=f"org-modo-lote-ok-{uuid4().hex[:8]}")
        usuario, dispositivo = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        item_online = _item(
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            secuencia=1,
            tipo="PRUEBA_LOTE_SOLO_ONLINE",
            modo="ONLINE",
        )

        resultados = sync_service.procesar_lote(
            db_session,
            FixedClock(MOMENTO),
            organizacion_id=organizacion.id,
            usuario_id=usuario,
            dispositivo_id=dispositivo,
            items=[item_online],
        )

        assert resultados[0].estado == "ACEPTADO"


class TestPropiedadDeLaColaAnivelServicio:
    """Tarea 8.5, a nivel de servicio: un ítem declarado con otro usuario u
    otro dispositivo hace rechazar TODO el lote, sin dejar ningún efecto."""

    def test_un_item_con_otro_usuario_rechaza_todo_el_lote(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-cola-usr-{uuid4().hex[:8]}")
        usuario_a, dispositivo = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, nombre_usuario="usuario-a"
        )
        usuario_b, _ = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, nombre_usuario="usuario-b"
        )
        db_session.commit()

        item_de_a = _item(usuario_id=usuario_a, dispositivo_id=dispositivo, secuencia=1)

        with pytest.raises(sync_service.ColaAjenaError) as exc_info:
            sync_service.procesar_lote(
                db_session,
                FixedClock(MOMENTO),
                organizacion_id=organizacion.id,
                usuario_id=usuario_b,  # sesión de B, comando declarado por A
                dispositivo_id=dispositivo,
                items=[item_de_a],
            )
        assert exc_info.value.codigo == "COLA_AJENA"

        assert db_session.scalar(_contar_por_operation_id(item_de_a.operation_id)) == 0

    def test_un_item_con_otro_dispositivo_rechaza_todo_el_lote(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session, slug=f"org-cola-disp-{uuid4().hex[:8]}")
        usuario, dispositivo_x = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        _, dispositivo_y = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, nombre_usuario=f"otro-{uuid4().hex[:8]}"
        )
        db_session.commit()

        item_de_x = _item(usuario_id=usuario, dispositivo_id=dispositivo_x, secuencia=1)

        with pytest.raises(sync_service.ColaAjenaError):
            sync_service.procesar_lote(
                db_session,
                FixedClock(MOMENTO),
                organizacion_id=organizacion.id,
                usuario_id=usuario,
                dispositivo_id=dispositivo_y,  # sesión desde Y, comando de X
                items=[item_de_x],
            )

        assert db_session.scalar(_contar_por_operation_id(item_de_x.operation_id)) == 0


# --- Nivel HTTP (`POST /api/v1/sync/comandos`) ------------------------------


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    """Cierra explícitamente el `Engine` propio de `crear_app` al terminar
    (recuperado vía `dependency_overrides`): sin esto, el pool de conexiones
    queda vivo hasta que el recolector de ciclos de CPython lo alcance, y una
    corrida completa de la suite agota `max_connections` de Postgres antes
    de eso."""
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion_http(database_url: str, _engine_de_sesion) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def _crear_usuario_y_dispositivo_http(
    sesion: Session, organizacion_id: UUID
) -> tuple[UUID, UUID, str]:
    """Igual que `_crear_usuario_y_dispositivo`, pero además devuelve el
    nombre de usuario -- el login real (`/auth/login`) lo necesita, y las
    pruebas HTTP de este archivo no tienen otra forma de recuperarlo."""
    nombre_usuario = f"vendedor-{uuid4().hex[:8]}"
    usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(
        sesion, organizacion_id, nombre_usuario=nombre_usuario
    )
    return usuario_id, dispositivo_id, nombre_usuario


def _login(cliente: TestClient, slug: str, usuario: str, dispositivo_id: str) -> str:
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": dispositivo_id,
            "nombre_dispositivo": "PC",
        },
    )
    assert respuesta.status_code == 200
    return respuesta.json()["access_token"]


def _item_http(*, usuario_id: str, dispositivo_id: str, secuencia: int) -> dict[str, object]:
    return {
        "operation_id": str(uuid4()),
        "tipo": "PRUEBA_LOTE",
        "version": 1,
        "modo": "ONLINE",
        "usuario_id": usuario_id,
        "dispositivo_id": dispositivo_id,
        "occurred_at": MOMENTO.isoformat(),
        "secuencia": secuencia,
        "app_version": "1.0.0",
        "contenido": {"resultado": "ACEPTADO"},
    }


class TestEndpointHttp:
    """Tarea 8.6: el endpoint real, con login real (mismo criterio que el
    ratchet INV-21: nunca un token fabricado a mano)."""

    def test_un_lote_valido_se_procesa_de_punta_a_punta(
        self, cliente: TestClient, sesion_http: Session
    ) -> None:
        organizacion = _crear_organizacion(sesion_http, slug=f"org-http-lote-{uuid4().hex[:8]}")
        usuario_id, dispositivo_id, nombre_usuario = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion.id
        )
        sesion_http.commit()
        # `dispositivo_id` real ya registrado por `_crear_dispositivo`: el
        # login lo reutiliza pasando el MISMO id (mismo criterio que
        # `test_bus_entrada_rest.py`, pero acá el dispositivo debe existir
        # de antemano porque `procesar_lote` lo consulta por su estado).
        access_token = _login(cliente, organizacion.slug, nombre_usuario, str(dispositivo_id))

        respuesta = cliente.post(
            "/api/v1/sync/comandos",
            json={
                "items": [
                    _item_http(
                        usuario_id=str(usuario_id),
                        dispositivo_id=str(dispositivo_id),
                        secuencia=1,
                    )
                ]
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert len(cuerpo["resultados"]) == 1
        assert cuerpo["resultados"][0]["estado"] == "ACEPTADO"

    def test_un_lote_de_51_comandos_se_rechaza_entero(
        self, cliente: TestClient, sesion_http: Session
    ) -> None:
        """Escenario "Un lote que excede el máximo se rechaza entero"."""
        organizacion = _crear_organizacion(sesion_http, slug=f"org-51-{uuid4().hex[:8]}")
        usuario_id, dispositivo_id, nombre_usuario = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion.id
        )
        sesion_http.commit()
        access_token = _login(cliente, organizacion.slug, nombre_usuario, str(dispositivo_id))

        items = [
            _item_http(usuario_id=str(usuario_id), dispositivo_id=str(dispositivo_id), secuencia=i)
            for i in range(1, 52)
        ]

        respuesta = cliente.post(
            "/api/v1/sync/comandos",
            json={"items": items},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 422

    def test_un_lote_sin_sesion_no_se_procesa(self, cliente: TestClient) -> None:
        """Escenario "Un lote sin sesión no se procesa" (SEG-06)."""
        respuesta = cliente.post("/api/v1/sync/comandos", json={"items": []})

        assert respuesta.status_code == 401


class TestAislamientoEntreOrganizacionesHttp:
    """Tarea 14.1 (change 04, grupo 14; INV-21, `docs/01-dominio.md` §20;
    `test_inv21_ratchet_rutas.py::COBERTURA_DE_AISLAMIENTO`, que ya declara
    esta ruta -- tarea 8.6 la agregó ahí mismo). Prueba de "acceso ajeno"
    real para `POST /sync/comandos`, con login real de dos organizaciones
    distintas (nunca un token fabricado a mano, mismo criterio que el resto
    del ratchet).

    Documentado explícitamente porque el patrón difiere del resto de
    `COBERTURA_DE_AISLAMIENTO`: esas rutas reciben el id ajeno en la URL y
    responden 404 (`RecursoNoEncontradoError`). Esta ruta no tiene id de
    recurso en la URL -- `organizacion_id` sale siempre del token
    (`sync/api.py`, nunca del cuerpo) -- así que no hay una consulta por id
    ajeno que pueda devolver "no encontrado". El aislamiento acá es
    estructural: el servidor compara el `usuario_id`/`dispositivo_id` que
    declara cada ítem del lote contra los de la SESIÓN (`ColaAjenaError`,
    SEG-02, `sync/service.py::procesar_lote`), y rechaza ante cualquier
    discrepancia -- sin distinguir si el id declarado pertenece a la propia
    organización o a otra, porque nunca llega a consultarlo. El código es
    403 (`ColaAjenaError.status_http`), no 404: no hay "recurso no
    encontrado" que ocultar, porque el servidor nunca busca ese id en la
    base -- lo rechaza antes, por la sola discrepancia con la sesión. Esta
    prueba confirma que ese rechazo estructural también cubre, en los
    hechos, el caso de una organización distinta (INV-21): ningún dato de
    la organización ajena se toca ni se expone, y el lote no deja rastro.
    """

    def test_una_organizacion_no_puede_sincronizar_declarando_usuario_de_otra(
        self, cliente: TestClient, sesion_http: Session
    ) -> None:
        organizacion_a = _crear_organizacion(sesion_http, slug=f"org-inv21-a-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(sesion_http, slug=f"org-inv21-b-{uuid4().hex[:8]}")
        usuario_a, dispositivo_a, _ = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion_a.id
        )
        _, dispositivo_b, nombre_b = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion_b.id
        )
        sesion_http.commit()

        access_token_b = _login(cliente, organizacion_b.slug, nombre_b, str(dispositivo_b))

        item_declarando_org_a = _item_http(
            usuario_id=str(usuario_a), dispositivo_id=str(dispositivo_a), secuencia=1
        )

        respuesta = cliente.post(
            "/api/v1/sync/comandos",
            json={"items": [item_declarando_org_a]},
            headers={"Authorization": f"Bearer {access_token_b}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "COLA_AJENA"
        assert (
            sesion_http.scalar(
                _contar_por_operation_id(UUID(cast(str, item_declarando_org_a["operation_id"])))
            )
            == 0
        )

    def test_una_organizacion_no_puede_sincronizar_declarando_dispositivo_de_otra(
        self, cliente: TestClient, sesion_http: Session
    ) -> None:
        """Triangulación (`usuario_id` ajeno arriba, `dispositivo_id` ajeno
        acá): mismo rechazo estructural, discrepancia distinta."""
        organizacion_a = _crear_organizacion(sesion_http, slug=f"org-inv21-c-{uuid4().hex[:8]}")
        organizacion_b = _crear_organizacion(sesion_http, slug=f"org-inv21-d-{uuid4().hex[:8]}")
        _, dispositivo_a, _ = _crear_usuario_y_dispositivo_http(sesion_http, organizacion_a.id)
        usuario_b, dispositivo_b, nombre_b = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion_b.id
        )
        sesion_http.commit()

        access_token_b = _login(cliente, organizacion_b.slug, nombre_b, str(dispositivo_b))

        item_declarando_dispositivo_de_a = _item_http(
            usuario_id=str(usuario_b), dispositivo_id=str(dispositivo_a), secuencia=1
        )

        respuesta = cliente.post(
            "/api/v1/sync/comandos",
            json={"items": [item_declarando_dispositivo_de_a]},
            headers={"Authorization": f"Bearer {access_token_b}"},
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "COLA_AJENA"


class TestUsuarioInactivoNoSeRechazaPorRuta:
    """ADR-028 D9.3-B (grupo 2, `tasks.md` 2.7): a diferencia del resto de
    las rutas de negocio (D9.1), `POST /sync/comandos` NO rechaza en bloque
    por ruta a un usuario que pasó a `INACTIVO` -- preserva el canal
    acotado para la cola offline (`design.md` D9, `identidad/api.py` sigue
    usando `obtener_contexto_autenticado`, no `requiere_permiso`). El lote
    se procesa por ítem igual que para un usuario activo: esto NO implica
    todavía la rama `PERMISO_REVOCADO` del inactivo (deuda nominada, `02`
    §6.3 paso 4, sin comandos offline reales hasta el change 15) -- solo
    fija que el canal de la ruta sigue abierto."""

    def test_lote_vacio_de_usuario_inactivo_responde_lista_vacia(
        self, cliente: TestClient, sesion_http: Session
    ) -> None:
        from sqlalchemy import text

        organizacion = _crear_organizacion(
            sesion_http, slug=f"org-inactivo-lote-1-{uuid4().hex[:8]}"
        )
        usuario_id, dispositivo_id, nombre_usuario = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion.id
        )
        sesion_http.commit()
        access_token = _login(cliente, organizacion.slug, nombre_usuario, str(dispositivo_id))

        sesion_http.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario_id)}
        )
        sesion_http.commit()

        respuesta = cliente.post(
            "/api/v1/sync/comandos",
            json={"items": []},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["resultados"] == []

    def test_tipo_desconocido_de_usuario_inactivo_da_rechazado_por_item(
        self, cliente: TestClient, sesion_http: Session
    ) -> None:
        """Triangulación: un lote no vacío tampoco se corta por ruta -- el
        procesamiento por ítem sigue su curso normal (un tipo no declarado
        en el catálogo da `RECHAZADO`, igual que para un usuario activo)."""
        from sqlalchemy import text

        organizacion = _crear_organizacion(
            sesion_http, slug=f"org-inactivo-lote-2-{uuid4().hex[:8]}"
        )
        usuario_id, dispositivo_id, nombre_usuario = _crear_usuario_y_dispositivo_http(
            sesion_http, organizacion.id
        )
        sesion_http.commit()
        access_token = _login(cliente, organizacion.slug, nombre_usuario, str(dispositivo_id))

        sesion_http.execute(
            text("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :id"), {"id": str(usuario_id)}
        )
        sesion_http.commit()

        item_de_tipo_desconocido = _item_http(
            usuario_id=str(usuario_id), dispositivo_id=str(dispositivo_id), secuencia=1
        )
        item_de_tipo_desconocido["tipo"] = "TIPO_QUE_NO_EXISTE"

        respuesta = cliente.post(
            "/api/v1/sync/comandos",
            json={"items": [item_de_tipo_desconocido]},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert len(cuerpo["resultados"]) == 1
        assert cuerpo["resultados"][0]["estado"] == "RECHAZADO"
