# ruff: noqa: F811
"""Tarea 6.7 (change 18b; `design.md` D2, D21; spec `identidad/pin-de-autorizacion`): el PIN de
`PIN_AUTORIZACION_ROTAR` sale del contenido del comando y viaja como dato efímero.

`POST /api/v1/identidad/usuarios/{id}/pin` separa el PIN del cuerpo antes de armar el contenido y
la huella y se lo entrega al handler por clausura (`SecretStr`). El contenido queda con
`usuario_id`. Nunca llega a la huella, a `comando`, a `comando_cuarentena`, a la auditoría, al
resultado ni a los registros; el lote no admite el tipo.

Reglas citadas: SEG-05, ADR-019, ADR-022, INV-01, INV-06, `02` §17.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_identidad_commands_maestros import (
    _crear_organizacion,
    _crear_usuario,
    _limpiar_datos_confirmados,  # noqa: F401  (fixture autouse)
    _login,
    cliente,  # noqa: F401  (fixture)
    sesion,  # noqa: F401  (fixture)
)

from app.commands import registro
from app.commands.errores import ContenidoDeComandoInvalidoError
from app.commands.huella import calcular_huella
from app.modules.identidad import repository

PIN = "735194"
URL_LOTE = "/api/v1/sync/comandos"


class Entorno:
    """Un administrador (`ADMIN_USUARIOS`) y un supervisor al que se le rota el PIN."""

    def __init__(self, cliente: TestClient, sesion: Session) -> None:
        self.cliente = cliente
        self.sesion = sesion
        self.organizacion = _crear_organizacion(sesion, f"org-pin-ef-{uuid4().hex[:8]}")
        _crear_usuario(
            sesion,
            self.organizacion.id,
            permisos=frozenset({"ADMIN_USUARIOS"}),
            nombre_usuario="admin1",
        )
        _crear_usuario(
            sesion,
            self.organizacion.id,
            permisos=frozenset({"AUTORIZAR_DESCUENTO"}),
            nombre_usuario="supervisor1",
        )
        sesion.commit()
        self.supervisor = repository.obtener_usuario_por_nombre_usuario(
            self.organizacion.id, "supervisor1", sesion
        )
        assert self.supervisor is not None
        self.token = _login(cliente, self.organizacion.slug, "admin1")
        self.url = f"/api/v1/identidad/usuarios/{self.supervisor.id}/pin"

    def rotar(self, pin: object, operation_id: UUID | None = None):  # type: ignore[no-untyped-def]
        return self.cliente.post(
            self.url,
            json={"pin": pin},
            headers={
                "Authorization": f"Bearer {self.token}",
                "Operation-Id": str(operation_id or uuid4()),
            },
        )

    def hash_vigente(self) -> str | None:
        self.sesion.rollback()
        self.sesion.refresh(self.supervisor)
        return self.supervisor.pin_autorizacion_hash

    def volcado(self, tabla: str) -> str:
        self.sesion.rollback()
        return str(
            self.sesion.execute(
                text(f"SELECT coalesce(string_agg(to_json(t)::text, ' '), '') FROM {tabla} t")
            ).scalar_one()
        )

    def sin_rastro(self, secreto: str) -> None:
        for tabla in ("comando", "comando_cuarentena", "auditoria", "observacion"):
            assert secreto not in self.volcado(tabla), tabla


def test_inv06_la_huella_de_la_rotacion_no_depende_del_pin_y_el_reenvio_no_vuelve_a_derivar(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    operacion = uuid4()

    primera = e.rotar(PIN, operacion)
    derivacion = e.hash_vigente()
    segunda = e.rotar("918273", operacion)  # otro PIN, misma operación

    assert (primera.status_code, segunda.status_code) == (204, 204)
    assert e.hash_vigente() == derivacion
    huella = sesion.execute(
        text("SELECT huella FROM comando WHERE operation_id = :o"), {"o": operacion}
    ).scalar_one()
    sesion.rollback()
    assert huella == calcular_huella({"usuario_id": str(e.supervisor.id)})


@pytest.mark.parametrize(
    ("pin", "estado"),
    [(PIN, 204), ("123456", 400), ("90817", 400)],
    ids=["valido", "trivial", "formato_invalido"],
)
def test_sec17_el_pin_no_queda_en_ningun_registro_ni_en_la_respuesta(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    pin: str,
    estado: int,
) -> None:
    e = Entorno(cliente, sesion)

    with caplog.at_level(logging.DEBUG):
        respuesta = e.rotar(pin)

    assert respuesta.status_code == estado
    assert pin not in respuesta.text
    assert pin not in caplog.text
    e.sin_rastro(pin)


def test_seg05_un_pin_invalido_o_trivial_deja_vigente_el_anterior(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    assert e.rotar(PIN).status_code == 204
    vigente = e.hash_vigente()

    for pin in ("123456", "90817", "abcdef"):
        respuesta = e.rotar(pin)
        assert respuesta.status_code == 400
        assert respuesta.json()["codigo"] == "IDENTIDAD_PIN_AUTORIZACION_INVALIDO"

    assert e.hash_vigente() == vigente


def test_sec17_un_cuerpo_invalido_responde_422_sin_el_valor(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)

    respuesta = e.rotar(917253)  # un número en vez de un texto

    assert respuesta.status_code == 422
    assert "917253" not in respuesta.text
    assert all("input" not in error for error in respuesta.json()["detail"])


def test_un_contenido_antiguo_con_el_pin_adentro_es_malformado() -> None:
    handler = registro.resolver_handler("PIN_AUTORIZACION_ROTAR", 1)

    with pytest.raises(ContenidoDeComandoInvalidoError) as error:
        registro.validar_contenido(handler, {"usuario_id": str(uuid4()), "pin": PIN})

    assert PIN not in error.value.mensaje
    registro.validar_contenido(handler, {"usuario_id": str(uuid4())})  # sin el PIN, es válido


def _item_rotacion(e: Entorno, modo: str, contenido: dict[str, object]) -> dict[str, object]:
    dispositivo = sesion_dispositivo(e)
    return {
        "operation_id": str(uuid4()),
        "tipo": "PIN_AUTORIZACION_ROTAR",
        "version": 1,
        "modo": modo,
        "usuario_id": dispositivo[0],
        "dispositivo_id": dispositivo[1],
        "occurred_at": "2026-10-22T12:00:00Z",
        "secuencia": 1,
        "app_version": "1.0.0",
        "contenido": contenido,
    }


def sesion_dispositivo(e: Entorno) -> tuple[str, str]:
    """El administrador y el único dispositivo con el que inició sesión."""
    e.sesion.rollback()
    usuario = e.sesion.execute(
        text("SELECT id FROM usuario WHERE organizacion_id = :o AND usuario = 'admin1'"),
        {"o": e.organizacion.id},
    ).scalar_one()
    dispositivo = e.sesion.execute(
        text("SELECT id FROM dispositivo WHERE organizacion_id = :o"), {"o": e.organizacion.id}
    ).scalar_one()
    return str(usuario), str(dispositivo)


@pytest.mark.parametrize("modo", ["ONLINE", "OFFLINE"])
@pytest.mark.parametrize("con_pin_adentro", [False, True], ids=["sin_pin", "con_pin"])
def test_syn06_el_lote_rechaza_la_rotacion_antes_de_reservar_y_sin_el_valor(
    cliente: TestClient,  # noqa: F811
    sesion: Session,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    modo: str,
    con_pin_adentro: bool,
) -> None:
    e = Entorno(cliente, sesion)
    contenido: dict[str, object] = {"usuario_id": str(e.supervisor.id)}
    if con_pin_adentro:
        contenido["pin"] = PIN
    item = _item_rotacion(e, modo, contenido)

    with caplog.at_level(logging.DEBUG):
        respuesta = cliente.post(
            URL_LOTE,
            json={"items": [item]},
            headers={"Authorization": f"Bearer {e.token}"},
        )

    assert respuesta.status_code == 200
    (resultado,) = respuesta.json()["resultados"]
    assert resultado["estado"] == "RECHAZADO"
    assert resultado["error_codigo"] == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert PIN not in respuesta.text
    assert PIN not in caplog.text
    assert e.volcado("comando") == ""
    assert e.hash_vigente() is None
    e.sin_rastro(PIN)


def test_syn06_un_dispositivo_revocado_no_guarda_la_rotacion_en_cuarentena(
    cliente: TestClient,
    sesion: Session,  # noqa: F811
) -> None:
    e = Entorno(cliente, sesion)
    item = _item_rotacion(e, "ONLINE", {"usuario_id": str(e.supervisor.id), "pin": PIN})
    sesion.execute(
        text("UPDATE dispositivo SET estado = 'REVOCADO' WHERE organizacion_id = :o"),
        {"o": e.organizacion.id},
    )
    sesion.commit()

    respuesta = cliente.post(
        URL_LOTE, json={"items": [item]}, headers={"Authorization": f"Bearer {e.token}"}
    )

    assert respuesta.status_code == 200
    (resultado,) = respuesta.json()["resultados"]
    assert resultado["error_codigo"] == "DISPOSITIVO_REVOCADO"
    assert e.volcado("comando_cuarentena") == ""
    e.sin_rastro(PIN)
