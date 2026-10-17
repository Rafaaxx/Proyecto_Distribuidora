"""Change 17, tarea 7.3: `POST /api/v1/cobranzas` (`COBRANZA_REGISTRAR`) por HTTP.

Mismo arnés que `test_pagos_proveedor_api.py`: PostgreSQL real, motor propio de la aplicación y
`login` real (nunca un access token fabricado). Cubre el contrato HTTP: `Operation-Id`
obligatorio, importes como string, Problem Details con el índice del medio en los errores de
medio y un código estable por regla, 201 con la cobranza y el saldo resultante, permiso,
idempotencia, `organizacion_id` solo del token y aislamiento (INV-21).

Reglas citadas: COB-01, COB-02, COB-03, INV-03, INV-06, INV-08, INV-21, SEG-06, SEG-07, TR-07,
TR-08, TR-09 y `design.md` D2, D4, D5, D13.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from cuentas_corrientes_utiles import (
    crear_cliente,
    crear_organizacion,
    crear_usuario_y_dispositivo,
)
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.clock import FixedClock
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.cuentas_corrientes import service as cuentas_service
from app.modules.identidad import repository as identidad_repository

MOMENTO = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-cobranzas-api"
URL_COBRANZAS = "/api/v1/cobranzas"

COBRADOR = frozenset({"REGISTRAR_COBRANZA"})


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente_http(database_url: str) -> Iterator[TestClient]:
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
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Entorno:
    """Una organización con su usuario cobrador, `Kiosco La Esquina` con saldo de `150000.00` y
    los medios "Efectivo" y "Transferencia" (esta exige referencia)."""

    def __init__(
        self,
        sesion: Session,
        *,
        permisos: frozenset[str] = COBRADOR,
        usuario: str = "cobrador1",
    ) -> None:
        self.sesion = sesion
        organizacion = crear_organizacion(sesion)
        self.org = organizacion.id
        self.slug = organizacion.slug
        self.usuario = usuario
        rol = identidad_repository.crear_rol(
            self.org,
            sesion,
            rol_id=nuevo_id(),
            nombre="Rol de prueba",
            tope_descuento=Decimal("0"),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in permisos:
            identidad_repository.asignar_permiso_a_rol(
                self.org, sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        identidad_repository.crear_usuario(
            self.org,
            sesion,
            usuario_id=nuevo_id(),
            usuario=usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
        )
        self.cliente_id = crear_cliente(sesion, self.org, nombre="Kiosco La Esquina")
        self.efectivo_id = self.crear_medio("Efectivo", requiere_referencia=False)
        self.transferencia_id = self.crear_medio("Transferencia", requiere_referencia=True)
        self.cargar_saldo_inicial(self.cliente_id, "150000.00")

    def crear_medio(self, nombre: str, *, requiere_referencia: bool, activo: bool = True) -> UUID:
        medio_id = uuid4()
        self.sesion.execute(
            text(
                "INSERT INTO medio_pago (id, organizacion_id, nombre, requiere_referencia, "
                "activo, creado_en, actualizado_en) "
                "VALUES (:id, :org, :nombre, :ref, :activo, :m, :m)"
            ),
            {
                "id": medio_id,
                "org": self.org,
                "nombre": nombre,
                "ref": requiere_referencia,
                "activo": activo,
                "m": MOMENTO,
            },
        )
        return medio_id

    def cargar_saldo_inicial(self, cliente_id: UUID, importe: str) -> None:
        usuario_id, dispositivo_id = crear_usuario_y_dispositivo(self.sesion, self.org)
        cuentas_service.registrar_saldo_inicial(
            self.org,
            self.sesion,
            FixedClock(MOMENTO),
            cuenta_tipo="CLIENTE",
            entidad_id=cliente_id,
            importe=importe,
            sentido="AUMENTA",
            occurred_at=MOMENTO,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            operation_id=uuid4(),
        )

    def entrar(self, cliente_http: TestClient) -> dict[str, str]:
        self.sesion.commit()
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": self.usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def cuerpo(self, **cambios: object) -> dict[str, Any]:
        base: dict[str, Any] = {
            "cobranza_id": str(uuid4()),
            "cliente_id": str(self.cliente_id),
            "importe": "50000.00",
            "medios": [
                {"medio_pago_id": str(self.efectivo_id), "importe": "30000.00"},
                {
                    "medio_pago_id": str(self.transferencia_id),
                    "importe": "20000.00",
                    "referencia": "0042",
                },
            ],
        }
        base.update(cambios)
        return base


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


def _contar(sesion: Session, tabla: str, organizacion_id: UUID) -> int:
    return int(
        sesion.execute(
            text(f"SELECT count(*) FROM {tabla} WHERE organizacion_id = :o"),
            {"o": organizacion_id},
        ).scalar_one()
    )


def _saldo(sesion: Session, organizacion_id: UUID, cliente_id: UUID) -> str:
    return str(
        sesion.execute(
            text("SELECT saldo FROM saldo_cuenta WHERE organizacion_id = :o AND entidad_id = :c"),
            {"o": organizacion_id, "c": cliente_id},
        ).scalar_one()
    )


# --- 201 con la cobranza y el saldo resultante (COB-01, COB-03, INV-03) ----------------


def test_registrar_una_cobranza_responde_201_con_la_cobranza_y_el_saldo_resultante(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-01, COB-02, COB-03, INV-03: los importes viajan y vuelven como string, y el saldo es
    el que queda después de aplicar la cobranza."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)
    cuerpo = entorno.cuerpo()

    respuesta = cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "cobranza_id": cuerpo["cobranza_id"],
        "estado": "CONFIRMADA",
        "importe": "50000.00",
        "saldo": "100000.00",
        "jornada_id": None,
    }
    assert _contar(sesion, "cobranza", entorno.org) == 1
    assert _contar(sesion, "cobranza_medio", entorno.org) == 2
    assert _saldo(sesion, entorno.org, entorno.cliente_id) == "100000.00"


def test_una_cobranza_de_mas_deja_el_saldo_a_favor_en_la_respuesta(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-03, D5: el saldo resultante negativo es el saldo a favor, sin observaciones."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS,
        json=entorno.cuerpo(
            importe="160000.00",
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "160000.00"}],
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["saldo"] == "-10000.00"


def test_el_reintento_con_el_mismo_operation_id_devuelve_lo_mismo_sin_duplicar(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-06: un reenvío idempotente del mismo `Operation-Id` devuelve exactamente lo mismo."""
    entorno = Entorno(sesion)
    headers = _con_op(entorno.entrar(cliente_http))
    cuerpo = entorno.cuerpo()

    primera = cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=headers)
    segunda = cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=headers)

    assert primera.status_code == 201
    assert segunda.json() == primera.json()
    assert _contar(sesion, "cobranza", entorno.org) == 1
    assert _saldo(sesion, entorno.org, entorno.cliente_id) == "100000.00"


# --- contrato HTTP (TR-07, SYN-01, INV-03, SEG-06, SEG-07, INV-21) ------------------------


def test_sin_operation_id_se_rechaza_con_400_y_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """TR-07, SYN-01."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(URL_COBRANZAS, json=entorno.cuerpo(), headers=headers)

    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "OPERATION_ID_REQUERIDO"
    assert _contar(sesion, "cobranza", entorno.org) == 0


def test_sin_sesion_responde_401(cliente_http: TestClient, sesion: Session) -> None:
    entorno = Entorno(sesion)
    entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS, json=entorno.cuerpo(), headers={"Operation-Id": str(uuid4())}
    )

    assert respuesta.status_code == 401


def test_sin_registrar_cobranza_responde_403_sin_efectos_ni_reserva(
    cliente_http: TestClient, sesion: Session
) -> None:
    """`01` §19, SEG-06."""
    entorno = Entorno(sesion, permisos=frozenset({"GESTIONAR_CLIENTES"}))
    headers = entorno.entrar(cliente_http)
    operation_id = uuid4()

    respuesta = cliente_http.post(
        URL_COBRANZAS, json=entorno.cuerpo(), headers=_con_op(headers, operation_id)
    )

    assert respuesta.status_code == 403
    assert _contar(sesion, "cobranza", entorno.org) == 0
    assert (
        sesion.execute(
            text("SELECT count(*) FROM comando WHERE operation_id = :id"), {"id": operation_id}
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize("campo", ["importe", "medio"])
def test_inv03_un_numero_json_en_lugar_de_un_string_se_rechaza(
    cliente_http: TestClient, sesion: Session, campo: str
) -> None:
    """INV-03: los importes viajan como string; un número JSON no pasa."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)
    cuerpo = entorno.cuerpo()
    if campo == "importe":
        cuerpo["importe"] = 50000.0
    else:
        cuerpo["medios"][0]["importe"] = 30000.0

    respuesta = cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 422
    assert _contar(sesion, "cobranza", entorno.org) == 0


def test_el_cuerpo_no_elige_la_organizacion(cliente_http: TestClient, sesion: Session) -> None:
    """INV-21, TR-08: la organización sale del token. Un campo extra se ignora en el cuerpo
    HTTP y NUNCA llega al contenido del comando."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS,
        json=entorno.cuerpo(organizacion_id=str(uuid4())),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 201
    organizacion = sesion.execute(
        text("SELECT organizacion_id FROM cobranza WHERE id = :id"),
        {"id": respuesta.json()["cobranza_id"]},
    ).scalar_one()
    assert organizacion == entorno.org


@pytest.mark.parametrize("observacion", ["a" * 501, " " * 501])
def test_una_observacion_de_mas_de_500_caracteres_responde_422_y_sin_efectos(
    cliente_http: TestClient, sesion: Session, observacion: str
) -> None:
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS, json=entorno.cuerpo(observacion=observacion), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    (error,) = respuesta.json()["detail"]
    assert error["loc"] == ["body", "observacion"]
    assert _contar(sesion, "cobranza", entorno.org) == 0


# --- Problem Details por código (COB-02, TR-09, INV-21, `02` §11) ---------------------------


@pytest.mark.parametrize("indice", [0, 1])
def test_un_error_de_medio_indica_el_medio_en_el_problem_details(
    cliente_http: TestClient, sesion: Session, indice: int
) -> None:
    """COB-02: la transferencia exige referencia; el medio que lo causó viene en el Problem
    Details con su posición desde 0, que cambia con la posición en la lista."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)
    efectivo = {"medio_pago_id": str(entorno.efectivo_id), "importe": "30000.00"}
    transferencia = {"medio_pago_id": str(entorno.transferencia_id), "importe": "20000.00"}
    medios = [efectivo, transferencia]
    medios.insert(indice, medios.pop(1))

    respuesta = cliente_http.post(
        URL_COBRANZAS, json=entorno.cuerpo(medios=medios), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    problema = respuesta.json()
    assert problema["codigo"] == "REFERENCIA_OBLIGATORIA"
    assert problema["medio"] == indice
    assert _contar(sesion, "cobranza", entorno.org) == 0


def test_medios_que_no_suman_responden_422_con_su_codigo(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-08."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS,
        json=entorno.cuerpo(
            medios=[{"medio_pago_id": str(entorno.efectivo_id), "importe": "49000.00"}]
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "MEDIOS_NO_SUMAN_IMPORTE"


def test_un_medio_inactivo_con_conexion_responde_422_con_el_medio(
    cliente_http: TestClient, sesion: Session
) -> None:
    """TR-09, D13 punto 4."""
    entorno = Entorno(sesion)
    inactivo = entorno.crear_medio("Billetera", requiere_referencia=False, activo=False)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS,
        json=entorno.cuerpo(
            importe="10000.00",
            medios=[{"medio_pago_id": str(inactivo), "importe": "10000.00"}],
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "MEDIO_PAGO_INACTIVO"
    assert respuesta.json()["medio"] == 0


def test_un_identificador_de_cobranza_repetido_responde_409(
    cliente_http: TestClient, sesion: Session
) -> None:
    """`02` §9, SYN-06."""
    entorno = Entorno(sesion)
    headers = entorno.entrar(cliente_http)
    cuerpo = entorno.cuerpo()
    assert (
        cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=_con_op(headers)).status_code == 201
    )

    respuesta = cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=_con_op(headers))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "COBRANZA_DUPLICADA"
    assert _contar(sesion, "cobranza", entorno.org) == 1


def test_el_consumidor_final_responde_422(cliente_http: TestClient, sesion: Session) -> None:
    """CLI-03, CC-08, D4 (precisión del apply 2026-10-16: 422, igual que `cuentas_corrientes`)."""
    entorno = Entorno(sesion)
    consumidor = crear_cliente(
        sesion, entorno.org, es_consumidor_final=True, nombre="Consumidor final"
    )
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS, json=entorno.cuerpo(cliente_id=str(consumidor)), headers=_con_op(headers)
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "CONSUMIDOR_FINAL_SIN_CUENTA"
    assert _contar(sesion, "cobranza", entorno.org) == 0


# --- aislamiento (INV-21, SEG-07) -----------------------------------------------------------


# Escenario: "Un comando sobre un recurso de otra organización no revela su existencia"
def test_inv21_un_cliente_de_otra_organizacion_responde_404_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    ajeno = Entorno(sesion, usuario="cobrador2")
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS,
        json=entorno.cuerpo(cliente_id=str(ajeno.cliente_id)),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    assert _contar(sesion, "cobranza", entorno.org) == 0
    assert _contar(sesion, "cobranza", ajeno.org) == 0
    assert _saldo(sesion, ajeno.org, ajeno.cliente_id) == "150000.00"


def test_inv21_un_medio_de_otra_organizacion_responde_404_con_el_medio(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    ajeno = Entorno(sesion, usuario="cobrador2")
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        URL_COBRANZAS,
        json=entorno.cuerpo(
            medios=[
                {"medio_pago_id": str(entorno.efectivo_id), "importe": "30000.00"},
                {"medio_pago_id": str(ajeno.efectivo_id), "importe": "20000.00"},
            ]
        ),
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["medio"] == 1
    assert _contar(sesion, "cobranza", entorno.org) == 0


# --- POST /cobranzas/{id}/anulacion (COB-05, CC-02, INV-06, INV-21, SEG-06) ---------------

ANULADOR = frozenset({"REGISTRAR_COBRANZA", "ANULAR_COBRANZA"})


def _crear_motivo(
    sesion: Session, organizacion_id: UUID, ambito: str = "ANULACION_COBRANZA"
) -> UUID:
    motivo_id = uuid4()
    sesion.execute(
        text(
            "INSERT INTO motivo (id, organizacion_id, ambito, nombre, activo, creado_en, "
            "actualizado_en) VALUES (:id, :o, :a, :n, true, :m, :m)"
        ),
        {
            "id": motivo_id,
            "o": organizacion_id,
            "a": ambito,
            "n": f"Motivo {motivo_id}",
            "m": MOMENTO,
        },
    )
    sesion.commit()
    return motivo_id


def _registrar(cliente_http: TestClient, entorno: Entorno, headers: dict[str, str]) -> str:
    cuerpo = entorno.cuerpo()
    respuesta = cliente_http.post(URL_COBRANZAS, json=cuerpo, headers=_con_op(headers))
    assert respuesta.status_code == 201
    return str(cuerpo["cobranza_id"])


def test_anular_una_cobranza_responde_200_con_el_saldo_devuelto(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-05, CC-02, CC-04, INV-03: el saldo vuelve a como estaba y viaja como string."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    motivo = _crear_motivo(sesion, entorno.org)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)

    respuesta = cliente_http.post(
        f"{URL_COBRANZAS}/{cobranza_id}/anulacion",
        json={"motivo_id": str(motivo), "observacion": "cheque 1234 sin fondos"},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "cobranza_id": cobranza_id,
        "estado": "ANULADA",
        "importe": "50000.00",
        "saldo": "150000.00",
    }
    assert _contar(sesion, "cobranza_anulacion", entorno.org) == 1


def test_anular_dos_veces_responde_409_y_el_reintento_con_el_mismo_operation_id_lo_repite(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-05, INV-06: otro `Operation-Id` da `COBRANZA_YA_ANULADA`; el mismo repite lo original."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    motivo = _crear_motivo(sesion, entorno.org)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)
    url = f"{URL_COBRANZAS}/{cobranza_id}/anulacion"
    operation_id = uuid4()

    primera = cliente_http.post(
        url, json={"motivo_id": str(motivo)}, headers=_con_op(headers, operation_id)
    )
    repetida = cliente_http.post(
        url, json={"motivo_id": str(motivo)}, headers=_con_op(headers, operation_id)
    )
    otra = cliente_http.post(url, json={"motivo_id": str(motivo)}, headers=_con_op(headers))

    assert (primera.status_code, repetida.status_code) == (200, 200)
    assert repetida.json() == primera.json()
    assert otra.status_code == 409
    assert otra.json()["codigo"] == "COBRANZA_YA_ANULADA"
    assert _contar(sesion, "cobranza_anulacion", entorno.org) == 1


def test_anular_sin_anular_cobranza_responde_403_sin_efectos(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-05, SEG-06."""
    entorno = Entorno(sesion)
    motivo = _crear_motivo(sesion, entorno.org)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)

    respuesta = cliente_http.post(
        f"{URL_COBRANZAS}/{cobranza_id}/anulacion",
        json={"motivo_id": str(motivo)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 403
    assert _contar(sesion, "cobranza_anulacion", entorno.org) == 0


def test_anular_con_motivo_invalido_o_observacion_larga_responde_422(
    cliente_http: TestClient, sesion: Session
) -> None:
    """COB-05, TR-09, D7."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    ajeno = _crear_motivo(sesion, entorno.org, "ANULACION_PAGO")
    bueno = _crear_motivo(sesion, entorno.org)
    headers = entorno.entrar(cliente_http)
    cobranza_id = _registrar(cliente_http, entorno, headers)
    url = f"{URL_COBRANZAS}/{cobranza_id}/anulacion"

    invalido = cliente_http.post(url, json={"motivo_id": str(ajeno)}, headers=_con_op(headers))
    larga = cliente_http.post(
        url, json={"motivo_id": str(bueno), "observacion": "a" * 501}, headers=_con_op(headers)
    )

    assert invalido.status_code == 422
    assert invalido.json()["codigo"] == "MOTIVO_INVALIDO"
    assert larga.status_code == 422
    assert _contar(sesion, "cobranza_anulacion", entorno.org) == 0


def test_inv21_anular_una_cobranza_de_otra_organizacion_responde_404(
    cliente_http: TestClient, sesion: Session
) -> None:
    """INV-21, SEG-07."""
    entorno = Entorno(sesion, permisos=ANULADOR)
    ajeno = Entorno(sesion, permisos=ANULADOR, usuario="otro1")
    motivo = _crear_motivo(sesion, entorno.org)
    headers_ajeno = ajeno.entrar(cliente_http)
    cobranza_ajena = _registrar(cliente_http, ajeno, headers_ajeno)
    headers = entorno.entrar(cliente_http)

    respuesta = cliente_http.post(
        f"{URL_COBRANZAS}/{cobranza_ajena}/anulacion",
        json={"motivo_id": str(motivo)},
        headers=_con_op(headers),
    )

    assert respuesta.status_code == 404
    assert _contar(sesion, "cobranza_anulacion", ajeno.org) == 0
