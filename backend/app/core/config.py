"""Configuración del backend, cargada desde variables de entorno.

Ver `docs/02-arquitectura.md` §3.1: la configuración vive en variables de
entorno, no en archivos versionados con valores reales.
"""

import re

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_JWT_SECRET_MIN_LARGO = 32
_VERSION_X_Y_Z = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


class Settings(BaseSettings):
    """Configuración de la aplicación.

    `database_url` es obligatoria: sin base de datos configurada, el backend
    no puede levantar (no hay valor por defecto razonable).
    """

    # `hide_input_in_errors`: los errores de validación no repiten los valores
    # recibidos (un secreto mal armado no debe aparecer en el registro).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    app_version: str = "dev"
    # Versión mínima de aplicación admitida para confirmar operaciones
    # nuevas (change 04, grupo 12, tarea 12.4, `design.md` D9, `02` §6.6):
    # configuración de DESPLIEGUE, no por organización -- reemplaza la
    # columna huérfana `configuracion_organizacion.app_version_minima`
    # (eliminada en la migración de este grupo, nunca se leía). `None` por
    # defecto: sin valor configurado, no restringe nada (ningún dispositivo
    # queda "desactualizado").
    app_version_minima: str | None = None
    log_level: str = "INFO"
    environment: str = "development"

    # Secreto de firma HS256 de los access token (`design.md` D4). Sin valor
    # por defecto: el backend no levanta sin él, igual que sin `database_url`
    # (`CLAUDE.md` §4: ningún secreto tiene valor por defecto).
    jwt_secret: str
    # Identificador de la clave activa, viaja en el encabezado `kid` del
    # token para permitir rotar el secreto sin invalidar tokens vigentes.
    jwt_kid: str = "1"

    @model_validator(mode="after")
    def _validar_produccion(self) -> "Settings":
        """Con `ENVIRONMENT=production` el backend no arranca con una
        configuración mal armada (change 27a, D6; `02` §6.6, §17). El error
        nombra la variable y nunca su valor. Fuera de producción no valida."""
        if self.environment != "production":
            return self
        if len(self.jwt_secret) < _JWT_SECRET_MIN_LARGO:
            raise ValueError(
                f"JWT_SECRET debe tener al menos {_JWT_SECRET_MIN_LARGO} caracteres en producción"
            )
        if not _VERSION_X_Y_Z.fullmatch(self.app_version):
            raise ValueError("APP_VERSION debe tener la forma X.Y.Z en producción")
        return self
