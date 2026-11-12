"""Texto que imprime `tareas ahora` (change 28, prueba manual 9.1): singular y plural correctos."""

import pytest

from app.tareas import corrida
from app.tareas.__main__ import _informar


def _resultado(
    resultado: str, diferencias: int, intentos_borrados: int | None
) -> corrida.ResultadoDeCorrida:
    return corrida.ResultadoDeCorrida(
        resultado=resultado,
        diferencias=diferencias,
        organizaciones=1,
        intentos_borrados=intentos_borrados,
    )


@pytest.mark.parametrize(
    ("diferencias", "esperado"),
    [
        (1, "Verificación de consistencia: 1 diferencia (no se corrige sola: avisar a soporte)"),
        (3, "Verificación de consistencia: 3 diferencias (no se corrigen solas: avisar a soporte)"),
    ],
)
def test_con_diferencias_concuerda_en_numero(
    capsys: pytest.CaptureFixture[str], diferencias: int, esperado: str
) -> None:
    _informar(_resultado(corrida.CON_DIFERENCIAS, diferencias, None))
    assert capsys.readouterr().out.strip() == esperado


@pytest.mark.parametrize(
    ("borrados", "esperado"),
    [
        (1, "Limpieza: 1 intento de inicio de sesión de más de 24 horas borrado"),
        (0, "Limpieza: 0 intentos de inicio de sesión de más de 24 horas borrados"),
        (134, "Limpieza: 134 intentos de inicio de sesión de más de 24 horas borrados"),
    ],
)
def test_limpieza_concuerda_en_numero(
    capsys: pytest.CaptureFixture[str], borrados: int, esperado: str
) -> None:
    _informar(_resultado(corrida.SIN_DIFERENCIAS, 0, borrados))
    salida = capsys.readouterr().out.splitlines()
    assert salida == ["Verificación de consistencia: sin diferencias", esperado]
