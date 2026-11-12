"""Exporta el esquema OpenAPI de la aplicación a un archivo estático.

`docs/02-arquitectura.md` §11: "El OpenAPI generado por FastAPI es el
contrato. El front genera sus tipos con openapi-typescript en cada cambio;
CI verifica que los tipos generados estén actualizados." (tarea 13.1 del
change 03).

No requiere una base de datos real ni un servidor corriendo: `crear_app`
solo construye un `Engine` de SQLAlchemy (perezoso, no conecta hasta que se
usa), así que basta con una URL de base de datos con forma válida y un
secreto JWT cualquiera para poder construir la aplicación y pedirle su
esquema OpenAPI. Nunca se usan estos valores para conectarse a nada.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://solo-para-generar-openapi@localhost/no-se-usa"
)
os.environ.setdefault("JWT_SECRET", "solo-para-generar-openapi-no-es-un-secreto-real")

from app.core.config import Settings  # noqa: E402  (después de fijar el entorno)
from app.main import crear_app  # noqa: E402

DESTINO = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    app = crear_app(Settings())  # type: ignore[call-arg]
    esquema = app.openapi()
    DESTINO.write_text(json.dumps(esquema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI exportado a {DESTINO}")


if __name__ == "__main__":
    main()
