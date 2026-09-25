"""Acceso a datos de `identidad` (`docs/02-arquitectura.md` §8).

Contrato no negociable: todo método público recibe `organizacion_id` como
primer parámetro obligatorio, y lo usa para filtrar toda consulta. Para
`organizacion` (la raíz sin padre) el filtro es sobre su propio `id`: el
`organizacion_id` de un método de este repositorio siempre identifica la
organización que la operación puede tocar, sin excepción (`tests/unit/
test_repositorios_organizacion_obligatoria.py`, tarea 6.3).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.identidad.models import (
    Auditoria,
    ConfiguracionOrganizacion,
    Dispositivo,
    IntentoLogin,
    Organizacion,
    Permiso,
    Rol,
    RolPermiso,
    SesionRefresh,
    Usuario,
)

# Excepción explícita y enumerable (tarea 6.3/6.4, mismo criterio que
# `TABLAS_GLOBALES_EXENTAS` de la tarea 3.1): funciones de este módulo que
# NO reciben `organizacion_id` como primer parámetro. Dos motivos, ambos
# porque la función es la fuente del propio filtro, no algo que lo reciba:
# el catálogo global `permiso` (D7), y la resolución de `organizacion_id`
# a partir del `slug` en el login (`ADR-021`, tarea 8.3).
FUNCIONES_SIN_ORGANIZACION_ID = frozenset(
    {
        "obtener_permiso_por_codigo",
        "listar_permisos",
        "obtener_organizacion_por_slug",
        "obtener_sesion_refresh_por_token_hash_global",
        # `intento_login` (grupo 11, `ADR-018`) no tiene `organizacion_id`
        # (ver docstring de la migración `e5f6a7b8c9d0` y del modelo
        # `IntentoLogin`): el límite por IP es transversal a organizaciones.
        "registrar_intento_login",
        "contar_intentos_fallidos_por_usuario",
        "contar_intentos_fallidos_por_ip",
        "obtener_intento_fallido_mas_antiguo_en_ventana_por_usuario",
        "obtener_intento_fallido_mas_antiguo_en_ventana_por_ip",
    }
)


def crear_organizacion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    nombre: str,
    slug: str,
    cuit: str | None,
    moneda: str,
    zona_horaria: str,
    estado: str,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Organizacion:
    """Crea `organizacion`. `organizacion_id` es el `id` que tendrá la
    organización nueva: es la única operación de este repositorio donde
    `organizacion_id` nace en vez de acotar una fila existente. `slug`
    resuelve la organización en el login antes de que exista un token
    (`ADR-021`); único en toda la base (no por organización: todavía no hay
    ninguna que la acote)."""
    organizacion = Organizacion(
        id=organizacion_id,
        nombre=nombre,
        slug=slug,
        cuit=cuit,
        moneda=moneda,
        zona_horaria=zona_horaria,
        estado=estado,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def obtener_organizacion_por_slug(slug: str, sesion: Session) -> Organizacion | None:
    """Único lookup de `organizacion` sin `organizacion_id` como filtro
    (`FUNCIONES_SIN_ORGANIZACION_ID`, `ADR-021`): es, por definición, cómo
    se obtiene ese filtro antes de que exista un token. Se usa exclusivamente
    para resolver el login (tarea 8.3); nunca dentro de una petición
    autenticada, que ya tiene `organizacion_id` del token."""
    consulta = select(Organizacion).where(Organizacion.slug == slug)
    return sesion.scalars(consulta).one_or_none()


def obtener_organizacion_por_id(organizacion_id: UUID, sesion: Session) -> Organizacion | None:
    return sesion.get(Organizacion, organizacion_id)


def crear_configuracion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    modo_impositivo: str,
    politica_credito_default: str,
    estado_facturacion_default: str,
    intentos_pin_max: int,
    descuento_manual_habilitado: bool,
    motivo_obligatorio_lista: bool,
    momento: datetime,
    lista_precio_default_id: UUID | None = None,
    tolerancia_offline_tipo: str | None = None,
    tolerancia_offline_valor: object | None = None,
    motivo_obligatorio_descuento: bool | None = None,
    redondeo_multiplo: object | None = None,
    redondeo_direccion: str | None = None,
    permite_consumidor_final: bool | None = None,
    cliente_consumidor_final_id: UUID | None = None,
    modalidad_iva_default: str | None = None,
    desvio_reloj_max_segundos: int | None = None,
    actualizado_por_id: UUID | None = None,
) -> ConfiguracionOrganizacion:
    """Crea la única fila de `configuracion_organizacion` de `organizacion_id`.

    La restricción de unicidad la impone la base (PK = `organizacion_id`,
    tarea 3.4): una segunda llamada para la misma organización falla en el
    `flush`/`commit` con `IntegrityError`, no se valida en Python.
    """
    configuracion = ConfiguracionOrganizacion(
        organizacion_id=organizacion_id,
        modo_impositivo=modo_impositivo,
        lista_precio_default_id=lista_precio_default_id,
        politica_credito_default=politica_credito_default,
        tolerancia_offline_tipo=tolerancia_offline_tipo,
        tolerancia_offline_valor=tolerancia_offline_valor,
        descuento_manual_habilitado=descuento_manual_habilitado,
        motivo_obligatorio_descuento=motivo_obligatorio_descuento,
        motivo_obligatorio_lista=motivo_obligatorio_lista,
        redondeo_multiplo=redondeo_multiplo,
        redondeo_direccion=redondeo_direccion,
        permite_consumidor_final=permite_consumidor_final,
        cliente_consumidor_final_id=cliente_consumidor_final_id,
        estado_facturacion_default=estado_facturacion_default,
        modalidad_iva_default=modalidad_iva_default,
        intentos_pin_max=intentos_pin_max,
        desvio_reloj_max_segundos=desvio_reloj_max_segundos,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(configuracion)
    sesion.flush()
    return configuracion


def obtener_configuracion(
    organizacion_id: UUID, sesion: Session
) -> ConfiguracionOrganizacion | None:
    return sesion.get(ConfiguracionOrganizacion, organizacion_id)


def actualizar_configuracion(
    organizacion_id: UUID,
    sesion: Session,
    *,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
    **campos: object,
) -> ConfiguracionOrganizacion | None:
    """Actualiza campos de la configuración de `organizacion_id`. Devuelve
    `None` sin tocar nada si la organización no tiene fila de configuración
    (nunca busca ni escribe en la de otra organización)."""
    configuracion = sesion.get(ConfiguracionOrganizacion, organizacion_id)
    if configuracion is None:
        return None

    for campo, valor in campos.items():
        setattr(configuracion, campo, valor)
    configuracion.actualizado_en = momento
    configuracion.actualizado_por_id = actualizado_por_id
    sesion.flush()
    return configuracion


# --- permiso (catálogo global, D7: excepción explícita sin organizacion_id) -


def obtener_permiso_por_codigo(codigo: str, sesion: Session) -> Permiso | None:
    return sesion.get(Permiso, codigo)


def listar_permisos(sesion: Session) -> list[Permiso]:
    return list(sesion.scalars(select(Permiso).order_by(Permiso.codigo)).all())


# --- rol ---------------------------------------------------------------


def crear_rol(
    organizacion_id: UUID,
    sesion: Session,
    *,
    rol_id: UUID,
    nombre: str,
    tope_descuento: Decimal,
    activo: bool,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Rol:
    rol = Rol(
        id=rol_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        tope_descuento=tope_descuento,
        activo=activo,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(rol)
    sesion.flush()
    return rol


def obtener_rol_por_id(organizacion_id: UUID, rol_id: UUID, sesion: Session) -> Rol | None:
    rol = sesion.get(Rol, rol_id)
    if rol is None or rol.organizacion_id != organizacion_id:
        return None
    return rol


def listar_roles(organizacion_id: UUID, sesion: Session) -> list[Rol]:
    consulta = select(Rol).where(Rol.organizacion_id == organizacion_id).order_by(Rol.nombre)
    return list(sesion.scalars(consulta).all())


def asignar_permiso_a_rol(
    organizacion_id: UUID, sesion: Session, *, rol_id: UUID, permiso_codigo: str
) -> RolPermiso:
    """Falla con `IntegrityError` si `permiso_codigo` no está en el
    catálogo global (FK `fk_rol_permiso__permiso`, `03` §4) o si `rol_id` no
    pertenece a `organizacion_id` (FK compuesta `fk_rol_permiso__rol`)."""
    fila = RolPermiso(organizacion_id=organizacion_id, rol_id=rol_id, permiso_codigo=permiso_codigo)
    sesion.add(fila)
    sesion.flush()
    return fila


def quitar_permiso_de_rol(
    organizacion_id: UUID, sesion: Session, *, rol_id: UUID, permiso_codigo: str
) -> None:
    fila = sesion.get(RolPermiso, (organizacion_id, rol_id, permiso_codigo))
    if fila is not None:
        sesion.delete(fila)
        sesion.flush()


def listar_permisos_de_rol(organizacion_id: UUID, rol_id: UUID, sesion: Session) -> list[str]:
    consulta = select(RolPermiso.permiso_codigo).where(
        RolPermiso.organizacion_id == organizacion_id, RolPermiso.rol_id == rol_id
    )
    return list(sesion.scalars(consulta).all())


# --- usuario -------------------------------------------------------------


def crear_usuario(
    organizacion_id: UUID,
    sesion: Session,
    *,
    usuario_id: UUID,
    usuario: str,
    nombre: str,
    email: str | None,
    password_hash: str,
    rol_id: UUID,
    estado: str,
    momento: datetime,
    tope_descuento_override: Decimal | None = None,
    actualizado_por_id: UUID | None = None,
) -> Usuario:
    fila = Usuario(
        id=usuario_id,
        organizacion_id=organizacion_id,
        usuario=usuario,
        nombre=nombre,
        email=email,
        password_hash=password_hash,
        rol_id=rol_id,
        tope_descuento_override=tope_descuento_override,
        estado=estado,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(fila)
    sesion.flush()
    return fila


def obtener_usuario_por_id(
    organizacion_id: UUID, usuario_id: UUID, sesion: Session
) -> Usuario | None:
    fila = sesion.get(Usuario, usuario_id)
    if fila is None or fila.organizacion_id != organizacion_id:
        return None
    return fila


def listar_usuarios_por_ids(
    organizacion_id: UUID, usuario_ids: frozenset[UUID], sesion: Session
) -> list[Usuario]:
    """Búsqueda por lote (change 06, tarea 14.4): un único `SELECT ... IN`
    en vez de `N` llamados a `obtener_usuario_por_id`. Filtra siempre por
    `organizacion_id` (INV-21): un id de otra organización no aparece en el
    resultado. Con `usuario_ids` vacío no consulta nada."""
    if not usuario_ids:
        return []
    consulta = select(Usuario).where(
        Usuario.organizacion_id == organizacion_id, Usuario.id.in_(usuario_ids)
    )
    return list(sesion.scalars(consulta).all())


def obtener_usuario_por_nombre_usuario(
    organizacion_id: UUID, nombre_usuario: str, sesion: Session
) -> Usuario | None:
    consulta = select(Usuario).where(
        Usuario.organizacion_id == organizacion_id, Usuario.usuario == nombre_usuario
    )
    return sesion.scalars(consulta).one_or_none()


def listar_usuarios_por_rol(organizacion_id: UUID, rol_id: UUID, sesion: Session) -> list[Usuario]:
    consulta = select(Usuario).where(
        Usuario.organizacion_id == organizacion_id, Usuario.rol_id == rol_id
    )
    return list(sesion.scalars(consulta).all())


def listar_usuarios(organizacion_id: UUID, sesion: Session) -> list[Usuario]:
    """Lista los usuarios de `organizacion_id` (tarea 10.7, endpoint de
    lectura usado también por la prueba de la tarea 10.8: ninguna respuesta
    de lectura de usuario puede contener la contraseña ni su derivación)."""
    consulta = (
        select(Usuario).where(Usuario.organizacion_id == organizacion_id).order_by(Usuario.usuario)
    )
    return list(sesion.scalars(consulta).all())


# --- dispositivo ---------------------------------------------------------


def crear_dispositivo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    dispositivo_id: UUID,
    nombre: str,
    prefijo: str,
    ultimo_correlativo: int,
    estado: str,
    momento: datetime,
    actualizado_por_id: UUID | None = None,
) -> Dispositivo:
    fila = Dispositivo(
        id=dispositivo_id,
        organizacion_id=organizacion_id,
        nombre=nombre,
        prefijo=prefijo,
        ultimo_correlativo=ultimo_correlativo,
        estado=estado,
        creado_en=momento,
        actualizado_en=momento,
        actualizado_por_id=actualizado_por_id,
    )
    sesion.add(fila)
    sesion.flush()
    return fila


def obtener_dispositivo_por_id(
    organizacion_id: UUID, dispositivo_id: UUID, sesion: Session
) -> Dispositivo | None:
    """`dispositivo` tiene clave primaria compuesta `(organizacion_id, id)`
    (`03` §4: `id` lo genera el dispositivo, no es globalmente único): el
    mismo `dispositivo_id` de otra organización no es la misma fila."""
    return sesion.get(Dispositivo, (organizacion_id, dispositivo_id))


def obtener_dispositivo_por_prefijo(
    organizacion_id: UUID, prefijo: str, sesion: Session
) -> Dispositivo | None:
    consulta = select(Dispositivo).where(
        Dispositivo.organizacion_id == organizacion_id, Dispositivo.prefijo == prefijo
    )
    return sesion.scalars(consulta).one_or_none()


def listar_dispositivos(organizacion_id: UUID, sesion: Session) -> list[Dispositivo]:
    consulta = (
        select(Dispositivo)
        .where(Dispositivo.organizacion_id == organizacion_id)
        .order_by(Dispositivo.creado_en)
    )
    return list(sesion.scalars(consulta).all())


# --- sesion_refresh --------------------------------------------------------


def crear_sesion_refresh(
    organizacion_id: UUID,
    sesion: Session,
    *,
    sesion_refresh_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    token_hash: str,
    familia_id: UUID,
    emitido_en: datetime,
    expira_en: datetime,
) -> SesionRefresh:
    fila = SesionRefresh(
        id=sesion_refresh_id,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        token_hash=token_hash,
        familia_id=familia_id,
        emitido_en=emitido_en,
        expira_en=expira_en,
    )
    sesion.add(fila)
    sesion.flush()
    return fila


def obtener_sesion_refresh_por_token_hash(
    organizacion_id: UUID, token_hash: str, sesion: Session
) -> SesionRefresh | None:
    consulta = select(SesionRefresh).where(
        SesionRefresh.organizacion_id == organizacion_id,
        SesionRefresh.token_hash == token_hash,
    )
    return sesion.scalars(consulta).one_or_none()


def obtener_sesion_refresh_por_token_hash_global(
    token_hash: str, sesion: Session
) -> SesionRefresh | None:
    """Único lookup de `sesion_refresh` sin `organizacion_id` como filtro
    (`FUNCIONES_SIN_ORGANIZACION_ID`, mismo criterio que `ADR-021`): la
    cookie de refresh no lleva la organización, así que renovar/cerrar
    sesión (tareas 8.5-8.8) la obtienen de la fila que encuentran por el
    hash del token, no al revés. `token_hash` es la derivación de un valor
    de 256 bits (`core/seguridad.py`): una colisión entre organizaciones es
    de probabilidad despreciable, no un vector de acceso cruzado real."""
    consulta = select(SesionRefresh).where(SesionRefresh.token_hash == token_hash)
    return sesion.scalars(consulta).one_or_none()


def revocar_familia_refresh(
    organizacion_id: UUID,
    sesion: Session,
    *,
    familia_id: UUID,
    momento: datetime,
    motivo: str,
) -> int:
    """Marca como revocadas todas las sesiones de refresh no revocadas de
    `familia_id` (tarea 8.6: detección de reuso corta toda la familia)."""
    consulta = (
        update(SesionRefresh)
        .where(
            SesionRefresh.organizacion_id == organizacion_id,
            SesionRefresh.familia_id == familia_id,
            SesionRefresh.revocado_en.is_(None),
        )
        .values(revocado_en=momento, motivo_revocacion=motivo)
    )
    resultado = sesion.execute(consulta)
    sesion.flush()
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


def revocar_sesiones_refresh_de_dispositivo(
    organizacion_id: UUID,
    sesion: Session,
    *,
    dispositivo_id: UUID,
    momento: datetime,
    motivo: str,
) -> int:
    """Marca como revocadas todas las sesiones de refresh no revocadas de
    `dispositivo_id` (tarea 8.10: revocar un dispositivo invalida sus
    refresh tokens). Devuelve cuántas filas tocó."""
    consulta = (
        update(SesionRefresh)
        .where(
            SesionRefresh.organizacion_id == organizacion_id,
            SesionRefresh.dispositivo_id == dispositivo_id,
            SesionRefresh.revocado_en.is_(None),
        )
        .values(revocado_en=momento, motivo_revocacion=motivo)
    )
    resultado = sesion.execute(consulta)
    sesion.flush()
    return int(resultado.rowcount or 0)  # type: ignore[attr-defined]


# --- auditoria (tabla de libro: solo inserción, INV-05) ---------------------


def crear_auditoria(
    organizacion_id: UUID,
    sesion: Session,
    *,
    auditoria_id: UUID,
    accion: str,
    entidad: str,
    occurred_at: datetime,
    registered_at: datetime,
    usuario_id: UUID | None = None,
    dispositivo_id: UUID | None = None,
    entidad_id: UUID | None = None,
    antes: dict[str, object] | None = None,
    despues: dict[str, object] | None = None,
    motivo_id: UUID | None = None,
    observacion: str | None = None,
    autorizador_id: UUID | None = None,
    operation_id: UUID | None = None,
    origen: str = "SISTEMA",
) -> Auditoria:
    """`origen` (change 04, tarea 10.5, D2): `'COMANDO'` (con
    `operation_id` obligatorio) para lo que sale del bus de comandos,
    `'SISTEMA'` (sin `operation_id`) para todo lo demás -- el default
    coincide con el `server_default` de la columna, pero quien conoce el
    origen real (`sync/service.py::procesar_comando`, o `identidad/
    service.py` para login/refresh) lo declara explícito en vez de
    depender de él en silencio. La base valida la correspondencia con el
    CHECK `ck_auditoria__operation_id_segun_origen` (migración
    `f6a7b8c9d0e1`): un valor inconsistente aquí llega a la base y falla
    ahí, no antes."""
    fila = Auditoria(
        id=auditoria_id,
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        antes=antes,
        despues=despues,
        motivo_id=motivo_id,
        observacion=observacion,
        autorizador_id=autorizador_id,
        operation_id=operation_id,
        origen=origen,
        occurred_at=occurred_at,
        registered_at=registered_at,
    )
    sesion.add(fila)
    sesion.flush()
    return fila


# --- intento_login (grupo 11, ADR-018: rate limit de login) ----------------
#
# Sin `organizacion_id` (ver `FUNCIONES_SIN_ORGANIZACION_ID` arriba): tabla
# de solo inserción (INV-05), `app_runtime` con `SELECT, INSERT` únicamente.


def registrar_intento_login(
    sesion: Session,
    *,
    intento_id: UUID,
    usuario_id: UUID | None,
    ip: str,
    exito: bool,
    momento: datetime,
) -> IntentoLogin:
    fila = IntentoLogin(id=intento_id, usuario_id=usuario_id, ip=ip, exito=exito, creado_en=momento)
    sesion.add(fila)
    sesion.flush()
    return fila


def _filtro_no_neutralizado_por_desbloqueo_manual(*, usuario_id: UUID) -> sa.ColumnElement[bool]:
    """Tarea 11.4 (desbloqueo manual): un desbloqueo se registra como una
    fila marcador con `exito=True` (único caso en que se inserta con
    éxito, ver `identidad/service.py::desbloquear_usuario`). Un intento
    fallido ESTRICTAMENTE anterior o simultáneo al último marcador no
    cuenta más (`<=`, no una ventana de tiempo): así se "neutraliza" sin
    `UPDATE`/`DELETE` (tabla de solo inserción, INV-05). Devuelve una
    condición SQLAlchemy lista para usar en un `.where(...)`."""
    subconsulta_ultimo_desbloqueo = (
        select(func.max(IntentoLogin.creado_en))
        .where(IntentoLogin.usuario_id == usuario_id, IntentoLogin.exito.is_(True))
        .scalar_subquery()
    )
    return sa.or_(
        subconsulta_ultimo_desbloqueo.is_(None),
        IntentoLogin.creado_en > subconsulta_ultimo_desbloqueo,
    )


def contar_intentos_fallidos_por_usuario(
    sesion: Session, *, usuario_id: UUID, desde: datetime
) -> int:
    """Cuenta con `SELECT COUNT(*)` en la base (`CLAUDE.md` §4: los reportes
    y conteos se calculan en la base, nunca trayendo filas a Python) los
    intentos fallidos de `usuario_id` con `creado_en >= desde` (ventana
    deslizante de 15 minutos, `ADR-018`), respetando el último desbloqueo
    manual si lo hay (tarea 11.4)."""
    consulta = (
        select(func.count())
        .select_from(IntentoLogin)
        .where(
            IntentoLogin.usuario_id == usuario_id,
            IntentoLogin.exito.is_(False),
            IntentoLogin.creado_en >= desde,
            _filtro_no_neutralizado_por_desbloqueo_manual(usuario_id=usuario_id),
        )
    )
    return int(sesion.execute(consulta).scalar_one())


def contar_intentos_fallidos_por_ip(sesion: Session, *, ip: str, desde: datetime) -> int:
    consulta = (
        select(func.count())
        .select_from(IntentoLogin)
        .where(
            IntentoLogin.ip == ip,
            IntentoLogin.exito.is_(False),
            IntentoLogin.creado_en >= desde,
        )
    )
    return int(sesion.execute(consulta).scalar_one())


def obtener_intento_fallido_mas_antiguo_en_ventana_por_usuario(
    sesion: Session, *, usuario_id: UUID, desde: datetime
) -> datetime | None:
    """El momento del intento fallido más antiguo todavía dentro de la
    ventana: cuando venza (`+ 15 minutos`), el bloqueo por usuario se
    levanta solo (tarea 11.4, desbloqueo automático). Respeta el último
    desbloqueo manual, igual que `contar_intentos_fallidos_por_usuario`."""
    consulta = select(func.min(IntentoLogin.creado_en)).where(
        IntentoLogin.usuario_id == usuario_id,
        IntentoLogin.exito.is_(False),
        IntentoLogin.creado_en >= desde,
        _filtro_no_neutralizado_por_desbloqueo_manual(usuario_id=usuario_id),
    )
    return sesion.execute(consulta).scalar_one_or_none()


def obtener_intento_fallido_mas_antiguo_en_ventana_por_ip(
    sesion: Session, *, ip: str, desde: datetime
) -> datetime | None:
    consulta = select(func.min(IntentoLogin.creado_en)).where(
        IntentoLogin.ip == ip,
        IntentoLogin.exito.is_(False),
        IntentoLogin.creado_en >= desde,
    )
    return sesion.execute(consulta).scalar_one_or_none()
