"""Escenario compartido de las pruebas de concurrencia de identidad (change 20b, grupo 6 y 4.6).

Una organización confirmada en la base, con administradores, roles y usuarios armados con
transacciones propias que SE CONFIRMAN (nunca rollback externo, `CLAUDE.md` §4). Cada comando se
envía por el bus (`sync_service.procesar_comando`) desde su propia sesión, igual que un worker
distinto de FastAPI (`02` §16.2).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.seguridad import hashear_password
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.sync import service as sync_service
from tests.concurrency.test_compras_concurrencia import (
    MOMENTO,
    RELOJ,
    _sesion_independiente,
)
from tests.integration.cuentas_corrientes_utiles import (
    crear_organizacion,
    crear_usuario_y_dispositivo,
)

ADMIN_USUARIOS = "ADMIN_USUARIOS"
VENDER = "VENDER"
CLAVE_ORIGINAL = "clave-original-de-la-prueba-5530"

Actor = tuple[UUID, UUID]
"""`(usuario_id, dispositivo_id)` de quien envía un comando."""


class EscenarioDeIdentidad:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        sesion = _sesion_independiente(database_url)
        try:
            self.org = crear_organizacion(sesion).id
            sesion.commit()
        finally:
            sesion.close()

    # --- armado de datos (cada pieza confirma) ------------------------------------------

    def crear_usuario(
        self, permisos: frozenset[str], *, con_clave: bool = False
    ) -> tuple[Actor, UUID]:
        """Un usuario activo con su rol propio y su dispositivo. Devuelve `(actor, rol_id)`."""
        sesion = _sesion_independiente(self.database_url)
        try:
            usuario_id, dispositivo_id = crear_usuario_y_dispositivo(
                sesion, self.org, permisos=permisos
            )
            rol_id = sesion.execute(
                text("SELECT rol_id FROM usuario WHERE id = :u"), {"u": usuario_id}
            ).scalar_one()
            if con_clave:
                sesion.execute(
                    text("UPDATE usuario SET password_hash = :h WHERE id = :u"),
                    {"h": hashear_password(CLAVE_ORIGINAL), "u": usuario_id},
                )
            sesion.commit()
            return (usuario_id, dispositivo_id), rol_id
        finally:
            sesion.close()

    def administrador(self) -> tuple[Actor, UUID]:
        return self.crear_usuario(frozenset({ADMIN_USUARIOS}))

    def rol_de_vendedor(self) -> UUID:
        _, rol_id = self.crear_usuario(frozenset({VENDER}))
        return rol_id

    def abrir_familia(self, usuario_id: UUID, dispositivo_id: UUID) -> None:
        """Una familia de refresh vigente del usuario en el dispositivo (un inicio de sesión)."""
        sesion = _sesion_independiente(self.database_url)
        try:
            sesion.execute(
                text(
                    "INSERT INTO sesion_refresh (id, organizacion_id, usuario_id, dispositivo_id, "
                    "token_hash, familia_id, emitido_en, expira_en) "
                    "VALUES (:id, :o, :u, :d, :h, :f, :e, :x)"
                ),
                {
                    "id": uuid4(),
                    "o": self.org,
                    "u": usuario_id,
                    "d": dispositivo_id,
                    "h": uuid4().hex,
                    "f": uuid4(),
                    "e": MOMENTO,
                    "x": MOMENTO.replace(year=MOMENTO.year + 1),
                },
            )
            sesion.commit()
        finally:
            sesion.close()

    def marcar_inactivo(self, usuario_id: UUID) -> None:
        """Deja INACTIVO a un usuario armado por el escenario (sin pasar por el comando)."""
        self._ejecutar("UPDATE usuario SET estado = 'INACTIVO' WHERE id = :u", u=usuario_id)

    def desactivar_rol(self, rol_id: UUID) -> None:
        self._ejecutar("UPDATE rol SET activo = false WHERE id = :r", r=rol_id)

    def _ejecutar(self, consulta: str, **parametros: object) -> None:
        sesion = _sesion_independiente(self.database_url)
        try:
            sesion.execute(text(consulta), parametros)
            sesion.commit()
        finally:
            sesion.close()

    def dispositivo(self) -> UUID:
        """Un dispositivo más de la organización (para sesiones en otro equipo)."""
        sesion = _sesion_independiente(self.database_url)
        try:
            _, dispositivo_id = crear_usuario_y_dispositivo(sesion, self.org)
            sesion.commit()
            return dispositivo_id
        finally:
            sesion.close()

    # --- comandos por el bus ------------------------------------------------------------

    def enviar(
        self,
        sesion: Session,
        actor: Actor,
        tipo: str,
        contenido: dict[str, Any],
        *,
        operation_id: UUID | None = None,
        **secretos: object,
    ) -> Any:
        usuario_id, dispositivo_id = actor
        sobre = SobreComando(
            operation_id=operation_id or uuid4(),
            tipo=tipo,
            version=1,
            modo="ONLINE",
            organizacion_id=self.org,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=MOMENTO,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,
        )
        registrado = registro.resolver_handler(sobre.tipo, sobre.version)
        validado = registro.validar_contenido(registrado, sobre.contenido)

        def _ejecutar(sesion_protegida: object) -> Any:
            return registrado.funcion(
                sobre,
                validado,
                sesion=sesion_protegida,  # type: ignore[arg-type]
                reloj=RELOJ,
                **secretos,
            )

        return sync_service.procesar_comando(
            sesion,
            RELOJ,
            sobre=sobre,
            huella=calcular_huella(sobre.contenido),
            ejecutar_handler=_ejecutar,
        )

    def baja(self, sesion: Session, actor: Actor, usuario_id: UUID) -> Any:
        return self.enviar(
            sesion, actor, "USUARIO_BAJA", {"usuario_id": str(usuario_id), "observacion": None}
        )

    def cambiar_rol(self, sesion: Session, actor: Actor, usuario_id: UUID, rol_id: UUID) -> Any:
        return self.enviar(
            sesion,
            actor,
            "USUARIO_ROL_CAMBIAR",
            {"usuario_id": str(usuario_id), "rol_id": str(rol_id)},
        )

    def cambiar_permisos(
        self, sesion: Session, actor: Actor, rol_id: UUID, permisos: list[str]
    ) -> Any:
        return self.enviar(
            sesion, actor, "ROL_PERMISOS_CAMBIAR", {"rol_id": str(rol_id), "permisos": permisos}
        )

    def baja_de_rol(self, sesion: Session, actor: Actor, rol_id: UUID) -> Any:
        return self.enviar(sesion, actor, "ROL_BAJA", {"rol_id": str(rol_id)})

    def alta_de_usuario(self, sesion: Session, actor: Actor, rol_id: UUID) -> Any:
        return self.enviar(
            sesion,
            actor,
            "USUARIO_CREAR",
            {
                "usuario": f"alta-{uuid4().hex[:8]}",
                "nombre": "Alta concurrente",
                "email": None,
                "rol_id": str(rol_id),
            },
            password=SecretStr("clave-de-la-prueba-8841"),
        )

    # --- lecturas confirmadas -----------------------------------------------------------

    def leer(self, consulta: str, **parametros: object) -> list[tuple[Any, ...]]:
        sesion = _sesion_independiente(self.database_url)
        try:
            filas = sesion.execute(text(consulta), {"o": self.org, **parametros}).all()
            return [tuple(fila) for fila in filas]
        finally:
            sesion.close()

    def administradores_activos(self) -> int:
        (fila,) = self.leer(
            "SELECT count(DISTINCT u.id) FROM usuario u "
            "JOIN rol r ON r.organizacion_id = u.organizacion_id AND r.id = u.rol_id "
            "JOIN rol_permiso p ON p.organizacion_id = r.organizacion_id AND p.rol_id = r.id "
            "WHERE u.organizacion_id = :o AND u.estado = 'ACTIVO' AND r.activo "
            "AND p.permiso_codigo = :p",
            p=ADMIN_USUARIOS,
        )
        return int(fila[0])

    def usuarios_activos_en_roles_de_baja(self) -> int:
        (fila,) = self.leer(
            "SELECT count(*) FROM usuario u "
            "JOIN rol r ON r.organizacion_id = u.organizacion_id AND r.id = u.rol_id "
            "WHERE u.organizacion_id = :o AND u.estado = 'ACTIVO' AND NOT r.activo"
        )
        return int(fila[0])

    def rol_activo(self, rol_id: UUID) -> bool:
        (fila,) = self.leer("SELECT activo FROM rol WHERE id = :r", r=rol_id)
        return bool(fila[0])

    def estado_de(self, usuario_id: UUID) -> str:
        (fila,) = self.leer("SELECT estado FROM usuario WHERE id = :u", u=usuario_id)
        return str(fila[0])

    def familias_vigentes(self, usuario_id: UUID) -> int:
        (fila,) = self.leer(
            "SELECT count(*) FROM sesion_refresh WHERE usuario_id = :u AND revocado_en IS NULL",
            u=usuario_id,
        )
        return int(fila[0])
