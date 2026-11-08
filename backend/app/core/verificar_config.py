"""Verificación previa de la configuración (change 27a, paso 0; D6).

La imagen de producción corre `python -m app.core.verificar_config` antes de
iniciar uvicorn: si la configuración está mal armada el contenedor sale con
código distinto de cero y el error nombra la variable, nunca su valor
(`docs/02-arquitectura.md` §17). Evita que el supervisor de workers de uvicorn
reintente indefinidamente una importación que no puede resultar bien.
"""

import sys

from pydantic import ValidationError

from app.core.config import Settings


def _nombre_variable(loc: tuple[int | str, ...], msg: str) -> str:
    """Nombre de la variable de entorno del error: el campo de `Settings` en
    mayúsculas; para las validaciones de producción (sin campo) el mensaje ya
    empieza por el nombre de la variable."""
    if loc:
        return str(loc[0]).upper()
    return msg.removeprefix("Value error, ").split(" ", 1)[0]


def main() -> int:
    try:
        Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        for error in exc.errors():
            variable = _nombre_variable(error["loc"], error["msg"])
            print(
                f"Configuración inválida: {variable} ({error['msg']})",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
