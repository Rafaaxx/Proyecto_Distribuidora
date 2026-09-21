"""Configuración del backend, cargada desde variables de entorno.

Ver `docs/02-arquitectura.md` §3.1: la configuración vive en variables de
entorno, no en archivos versionados con valores reales.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación.

    `database_url` es obligatoria: sin base de datos configurada, el backend
    no puede levantar (no hay valor por defecto razonable).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_version: str = "dev"
    log_level: str = "INFO"
    environment: str = "development"

    # Secreto de firma HS256 de los access token (`design.md` D4). Sin valor
    # por defecto: el backend no levanta sin él, igual que sin `database_url`
    # (`CLAUDE.md` §4: ningún secreto tiene valor por defecto).
    jwt_secret: str
    # Identificador de la clave activa, viaja en el encabezado `kid` del
    # token para permitir rotar el secreto sin invalidar tokens vigentes.
    jwt_kid: str = "1"
