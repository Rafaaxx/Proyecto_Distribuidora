"""Credenciales efímeras de un comando (change 18b, `design.md` D2, `02` §17, ADR-019).

Un secreto de autorización (hoy el PIN de un supervisor) viaja FUERA del contenido del comando:
la ruta lo separa del cuerpo antes de armar el contenido y calcular la huella, y lo entrega al
handler por clausura como `SecretStr`. El bus no lo ve, así que no entra a la huella, a
`comando`, a `comando_cuarentena`, a la auditoría, al resultado ni a los registros.

No importa FastAPI ni SQLAlchemy ni módulos de negocio (contrato `commands-no-modulos`).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import SecretStr


@dataclass(frozen=True)
class CredencialDePin:
    """El PIN que un supervisor escribió para autorizar una excepción. `repr` del `SecretStr`
    ya lo oculta; no se persiste ni se registra nunca."""

    autorizador_id: UUID
    pin: SecretStr
