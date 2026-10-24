"""Ratchet de la tarea 22.6 (change 18b, `design.md` D2 y D23, ADR-056; cita `02` §17, SEG-05):
ningún secreto viaja en el contenido de un comando.

1. Ningún esquema de contenido registrado (ni los que anida) declara un campo `SecretStr` ni de un
   nombre de secreto (`password`, `password_actual`, `contrasena`, `pin`, `secreto`). El contenido
   entra a la huella, a `comando`, a `comando_cuarentena` y a la auditoría.
2. Todo handler que recibe un secreto por clausura (parámetro `SecretStr` o con nombre de secreto)
   está declarado con `exige_credenciales_efimeras`, de modo que el lote lo rechaza. La única
   excepción explícita es `VENTA_CONFIRMAR`, cuyas credenciales son opcionales (D2): por el lote
   llega sin ellas.
"""

from __future__ import annotations

import inspect
import typing

import pytest
from pydantic import BaseModel, SecretStr

import app.main  # noqa: F401  (importar `app.main` puebla catálogo y registro reales)
from app.commands import catalogo, registro

NOMBRES_DE_SECRETO = frozenset({"password", "password_actual", "contrasena", "pin", "secreto"})
CON_CREDENCIALES_OPCIONALES = frozenset({"VENTA_CONFIRMAR"})
"""`VENTA_CONFIRMAR` recibe `credenciales` opcionales por clausura (D2), sin la bandera."""

_REGISTRO_REAL = dict(registro._REGISTRO)
_CATALOGO_REAL = dict(catalogo._CATALOGO)


def _secretos_declarados(esquema: type[BaseModel], visto: set[type]) -> list[str]:
    """Campos del esquema (y de los esquemas que anida) que son un secreto."""
    if esquema in visto:
        return []
    visto.add(esquema)
    encontrados: list[str] = []
    for nombre, campo in esquema.model_fields.items():
        if nombre.lower() in NOMBRES_DE_SECRETO:
            encontrados.append(f"{esquema.__name__}.{nombre} (nombre de secreto)")
        pendientes = [campo.annotation]
        while pendientes:
            anotacion = pendientes.pop()
            if anotacion is SecretStr:
                encontrados.append(f"{esquema.__name__}.{nombre} (SecretStr)")
            elif isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
                encontrados.extend(_secretos_declarados(anotacion, visto))
            pendientes.extend(typing.get_args(anotacion))
    return encontrados


def test_ningun_esquema_de_contenido_declara_un_secreto() -> None:
    assert _REGISTRO_REAL, "el registro real no se pobló al importar los módulos de negocio"
    con_secretos = [
        f"{h.tipo} v{h.version}: {campo}"
        for h in _REGISTRO_REAL.values()
        for campo in _secretos_declarados(h.esquema, set())
    ]
    assert not con_secretos, f"Contenidos con secretos: {con_secretos}"


def _recibe_secretos_por_clausura(funcion: typing.Callable[..., object]) -> list[str]:
    parametros = inspect.signature(funcion).parameters
    return [
        nombre
        for nombre, parametro in parametros.items()
        if nombre in NOMBRES_DE_SECRETO
        or "SecretStr" in str(parametro.annotation)
        or nombre == "credenciales"
    ]


def test_todo_tipo_que_recibe_secretos_por_clausura_exige_credenciales_efimeras() -> None:
    sin_bandera = [
        f"{h.tipo} v{h.version}: {_recibe_secretos_por_clausura(h.funcion)}"
        for h in _REGISTRO_REAL.values()
        if _recibe_secretos_por_clausura(h.funcion)
        and h.tipo not in CON_CREDENCIALES_OPCIONALES
        and not _CATALOGO_REAL[h.tipo].exige_credenciales_efimeras
    ]
    assert not sin_bandera, (
        f"Handlers con secretos sin `exige_credenciales_efimeras`: {sin_bandera}"
    )


def test_los_tres_tipos_con_secretos_obligatorios_estan_marcados() -> None:
    marcados = {t.tipo for t in _CATALOGO_REAL.values() if t.exige_credenciales_efimeras}
    assert marcados == {
        "USUARIO_CREAR",
        "PIN_AUTORIZACION_ROTAR",
        "PIN_AUTORIZACION_PROPIO_DEFINIR",
    }


class _ConPin(BaseModel):
    usuario_id: str
    pin: SecretStr


class _Anidado(BaseModel):
    interno: list[_ConPin]


def test_el_ratchet_detecta_un_secreto_en_un_esquema_y_en_uno_anidado() -> None:
    assert _secretos_declarados(_ConPin, set()) == [
        "_ConPin.pin (nombre de secreto)",
        "_ConPin.pin (SecretStr)",
    ]
    assert len(_secretos_declarados(_Anidado, set())) == 2


def test_el_ratchet_detecta_un_handler_con_secreto_por_clausura() -> None:
    def con_pin(sobre: object, contenido: object, *, sesion: object, reloj: object, pin: SecretStr):
        return None

    def sin_nada(sobre: object, contenido: object, *, sesion: object, reloj: object):
        return None

    assert _recibe_secretos_por_clausura(con_pin) == ["pin"]
    assert _recibe_secretos_por_clausura(sin_nada) == []


@pytest.mark.parametrize("tipo", sorted(CON_CREDENCIALES_OPCIONALES))
def test_la_excepcion_de_credenciales_opcionales_sigue_siendo_valida(tipo: str) -> None:
    """Si `VENTA_CONFIRMAR` dejara de recibir credenciales, la excepción sobraría."""
    funcion = next(h.funcion for h in _REGISTRO_REAL.values() if h.tipo == tipo)
    assert _recibe_secretos_por_clausura(funcion)
