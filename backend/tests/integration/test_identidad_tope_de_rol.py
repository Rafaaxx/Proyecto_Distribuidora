"""Change 16, tareas 13.1 y 13.2: `ROL_TOPE_DESCUENTO_DEFINIR` v1 por el bus y por HTTP
(`PUT /api/v1/identidad/roles/{rol_id}/tope-descuento`, `GET /api/v1/identidad/roles`), contra
PostgreSQL real (spec delta `identidad/usuarios-y-roles`, requisito "El tope de descuento de un
rol se define por comando"; `design.md` D13, D18).

El comando cambia SOLO `rol.tope_descuento`: no toca los permisos del rol, el tope propio de los
usuarios, el PIN, el token ni `GET /yo`.

Reglas citadas: DSC-06, TR-02, INV-01, INV-03, INV-06, INV-21, AUD-01, AUD-02, SEG-06, SEG-07,
SYN-02.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from descuentos_utiles import RELOJ
from descuentos_utiles import Entorno as EntornoDeDatos
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.commands.errores import ComandoInconsistenteError
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.errors import PermisoRequeridoError
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.descuentos import service as descuentos_service
from app.modules.identidad import commands as _identidad_commands  # noqa: F401 (registra)
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad import service as identidad_service
from app.modules.identidad.domain.usuarios import TopeDescuentoFueraDeRangoError
from app.modules.identidad.models import Auditoria, Rol
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-tope-de-rol"
DEFINIR = "ROL_TOPE_DESCUENTO_DEFINIR"
URL_ROLES = "/api/v1/identidad/roles"
ADMIN_USUARIOS = frozenset({"ADMIN_USUARIOS"})
DM = "DESCUENTO_MANUAL"


@pytest.fixture(autouse=True)
def _limpiar_datos_confirmados(database_url: str) -> Iterator[None]:
    yield
    engine = crear_engine(database_url)
    with engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE organizacion CASCADE"))
    engine.dispose()


@pytest.fixture
def cliente(database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, database_url=database_url, jwt_secret=JWT_SECRET, jwt_kid="1"
    )
    app = crear_app(settings)
    engine = app.dependency_overrides[sistema._get_engine]()
    try:
        yield TestClient(app)
    finally:
        engine.dispose()


@pytest.fixture
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


class Entorno(EntornoDeDatos):
    """Una organización cuyo usuario de los comandos tiene `ADMIN_USUARIOS`, con atajos para
    roles, usuarios que entran por `login` y lecturas frescas de lo escrito."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, permisos=ADMIN_USUARIOS)
        self.sesion.commit()
        self.slug = sesion.execute(
            text("SELECT slug FROM organizacion WHERE id = :o"), {"o": self.org}
        ).scalar_one()
        self.sesion.execute(
            text(
                "UPDATE configuracion_organizacion SET descuento_manual_habilitado = true "
                "WHERE organizacion_id = :o"
            ),
            {"o": self.org},
        )

    def crear_rol(
        self,
        nombre: str,
        tope: str = "0.000000",
        *,
        permisos: frozenset[str] = frozenset(),
        org: UUID | None = None,
    ) -> Rol:
        organizacion = org or self.org
        rol = identidad_repository.crear_rol(
            organizacion,
            self.sesion,
            rol_id=nuevo_id(),
            nombre=nombre,
            tope_descuento=Decimal(tope),
            activo=True,
            momento=MOMENTO,
        )
        for codigo in sorted(permisos):
            identidad_repository.asignar_permiso_a_rol(
                organizacion, self.sesion, rol_id=rol.id, permiso_codigo=codigo
            )
        self.sesion.commit()
        return rol

    def crear_usuario(
        self, rol: Rol, *, tope_propio: str | None = None, org: UUID | None = None
    ) -> tuple[UUID, str]:
        nombre_usuario = f"usuario-{uuid4().hex[:8]}"
        usuario = identidad_repository.crear_usuario(
            org or self.org,
            self.sesion,
            usuario_id=nuevo_id(),
            usuario=nombre_usuario,
            nombre="Persona de prueba",
            email=None,
            password_hash=hashear_password(PASSWORD),
            rol_id=rol.id,
            estado="ACTIVO",
            momento=MOMENTO,
            tope_descuento_override=None if tope_propio is None else Decimal(tope_propio),
        )
        self.sesion.commit()
        return usuario.id, nombre_usuario

    def entrar(self, cliente_http: TestClient, nombre_usuario: str) -> dict[str, str]:
        respuesta = cliente_http.post(
            "/api/v1/auth/login",
            json={
                "organizacion_slug": self.slug,
                "usuario": nombre_usuario,
                "contrasena": PASSWORD,
                "dispositivo_id": str(uuid4()),
                "nombre_dispositivo": "PC",
            },
        )
        assert respuesta.status_code == 200, respuesta.text
        return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}

    def con_permisos(self, cliente_http: TestClient, *permisos: str) -> dict[str, str]:
        rol = self.crear_rol(f"Rol {uuid4().hex[:6]}", permisos=frozenset(permisos))
        _, nombre = self.crear_usuario(rol)
        return self.entrar(cliente_http, nombre)

    def rol(self, rol_id: UUID) -> Rol:
        return self.sesion.scalars(
            select(Rol)
            .where(Rol.organizacion_id == self.org, Rol.id == rol_id)
            .execution_options(populate_existing=True)
        ).one()

    def rol_de(self, org: UUID, rol_id: UUID) -> Rol:
        return self.sesion.scalars(
            select(Rol)
            .where(Rol.organizacion_id == org, Rol.id == rol_id)
            .execution_options(populate_existing=True)
        ).one()

    def permisos_de(self, rol_id: UUID) -> list[str]:
        return sorted(identidad_repository.listar_permisos_de_rol(self.org, rol_id, self.sesion))

    def auditorias_del_tope(self) -> list[Auditoria]:
        """Las de la ESCRITURA (entidad `rol`), no la fila genérica que el bus deja por cada
        comando (entidad `comando`)."""
        return list(
            self.sesion.scalars(
                select(Auditoria)
                .where(
                    Auditoria.organizacion_id == self.org,
                    Auditoria.accion == DEFINIR,
                    Auditoria.entidad == "rol",
                )
                .execution_options(populate_existing=True)
            )
        )

    def definir(self, rol_id: UUID, tope: Any, *, operation_id: UUID | None = None) -> Any:
        return self.enviar(
            DEFINIR, {"rol_id": str(rol_id), "tope_descuento": tope}, operation_id=operation_id
        )


@pytest.fixture
def entorno(sesion: Session) -> Entorno:
    return Entorno(sesion)


def _con_op(headers: dict[str, str], operation_id: UUID | None = None) -> dict[str, str]:
    return {**headers, "Operation-Id": str(operation_id or uuid4())}


# --- por el bus (13.1) ----------------------------------------------------------------------------


def test_definir_el_tope_del_vendedor_no_cambia_sus_permisos(entorno: Entorno) -> None:
    """Escenario "Definir el tope de un rol"."""
    vendedor = entorno.crear_rol("Vendedor/Repartidor", permisos=frozenset({DM, "VENDER"}))

    comando = entorno.definir(vendedor.id, "0.050000")

    assert comando.estado == "ACEPTADO"
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0.050000")
    assert entorno.permisos_de(vendedor.id) == [DM, "VENDER"]
    assert comando.resultado == {
        "rol_id": str(vendedor.id),
        "nombre": "Vendedor/Repartidor",
        "activo": True,
        "tope_descuento": "0.050000",
    }


def test_el_tope_nuevo_rige_en_la_siguiente_evaluacion(entorno: Entorno) -> None:
    """Escenario "El tope nuevo rige en la siguiente evaluación" (DSC-06): con el 0 de la
    plantilla un 3% pide autorización; con el 5% definido, no."""
    vendedor = entorno.crear_rol("Vendedor", permisos=frozenset({DM}))
    usuario_id, _ = entorno.crear_usuario(vendedor)

    def evaluar() -> Any:
        return descuentos_service.evaluar_descuento_manual(
            entorno.org,
            entorno.sesion,
            usuario_id=usuario_id,
            porcentaje_maximo=Decimal("0.030000"),
            motivo=None,
            autorizador_id=None,
        )

    with pytest.raises(Exception) as antes:  # noqa: B017
        evaluar()
    assert antes.value.codigo == "AUTORIZACION_REQUERIDA"  # type: ignore[attr-defined]

    entorno.definir(vendedor.id, "0.050000")
    entorno.sesion.expire_all()

    resultado = evaluar()
    assert (resultado.tope_aplicado, resultado.resolucion) == (
        Decimal("0.050000"),
        "DENTRO_DEL_TOPE",
    )


def test_el_tope_propio_de_un_usuario_no_cambia(entorno: Entorno) -> None:
    """Escenario "El tope propio de un usuario no cambia" (`tope_descuento_override`)."""
    vendedor = entorno.crear_rol("Vendedor", "0.100000", permisos=frozenset({DM}))
    usuario_id, _ = entorno.crear_usuario(vendedor, tope_propio="0.080000")

    entorno.definir(vendedor.id, "0.050000")
    entorno.sesion.expire_all()

    datos = identidad_service.obtener_datos_para_descuento_manual(
        entorno.org, usuario_id, entorno.sesion
    )
    assert datos is not None
    assert (datos.tope_rol, datos.tope_propio) == (Decimal("0.050000"), Decimal("0.080000"))


def test_sin_admin_usuarios_se_rechaza_con_permiso_requerido(entorno: Entorno) -> None:
    """Escenario "Sin permiso"."""
    vendedor = entorno.crear_rol("Vendedor")
    entorno.actuar_con_permisos(frozenset({"GESTIONAR_DESCUENTOS"}))

    with pytest.raises(PermisoRequeridoError):
        entorno.definir(vendedor.id, "0.050000")

    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0")
    assert entorno.auditorias_del_tope() == []


@pytest.mark.parametrize("tope", ["-0.010000", "1.000001", "0.1234567", "2"])
def test_un_tope_fuera_de_rango_se_rechaza_y_no_cambia(entorno: Entorno, tope: str) -> None:
    """Escenario "Tope fuera de rango": negativo, mayor que 1 o con siete decimales (TR-02)."""
    vendedor = entorno.crear_rol("Vendedor", "0.020000")

    with pytest.raises(TopeDescuentoFueraDeRangoError) as error:
        entorno.definir(vendedor.id, tope)

    assert error.value.codigo == "IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO"
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0.020000")
    assert entorno.auditorias_del_tope() == []


@pytest.mark.parametrize("tope", ["0", "0.000000", "0.5", "1", "1.000000"])
def test_los_extremos_y_las_formas_cortas_se_aceptan(entorno: Entorno, tope: str) -> None:
    vendedor = entorno.crear_rol("Vendedor", "0.020000")

    entorno.definir(vendedor.id, tope)

    assert entorno.rol(vendedor.id).tope_descuento == Decimal(tope)


def test_un_rol_de_otra_organizacion_se_rechaza_y_no_cambia(
    entorno: Entorno, sesion: Session
) -> None:
    """Escenario "Rol de otra organización" (INV-21, SEG-07)."""
    ajena = Entorno(sesion)
    rol_ajeno = ajena.crear_rol("Vendedor ajeno", "0.020000")

    comando = entorno.definir(rol_ajeno.id, "0.050000")

    assert comando.estado == "RECHAZADO"
    assert comando.error_codigo == "ROL_NO_ENCONTRADO"
    assert ajena.rol_de(ajena.org, rol_ajeno.id).tope_descuento == Decimal("0.020000")
    assert ajena.auditorias_del_tope() == [] and entorno.auditorias_del_tope() == []


def test_aud01_aud02_queda_una_sola_fila_de_auditoria_con_antes_despues_y_operation_id(
    entorno: Entorno,
) -> None:
    """Escenario "El cambio queda auditado"."""
    vendedor = entorno.crear_rol("Vendedor")

    comando = entorno.definir(vendedor.id, "0.050000")

    (auditoria,) = entorno.auditorias_del_tope()
    assert auditoria.antes == {"tope_descuento": "0.000000"}
    assert auditoria.despues == {"tope_descuento": "0.050000"}
    assert auditoria.entidad_id == vendedor.id
    assert auditoria.usuario_id == entorno.usuario_id
    assert auditoria.operation_id == comando.operation_id
    assert auditoria.origen == "COMANDO"


def test_inv06_el_doble_envio_devuelve_el_resultado_original_con_una_sola_auditoria(
    entorno: Entorno,
) -> None:
    """Escenario "Doble envío"."""
    vendedor = entorno.crear_rol("Vendedor")
    operation_id = uuid4()

    primero = entorno.definir(vendedor.id, "0.050000", operation_id=operation_id)
    segundo = entorno.definir(vendedor.id, "0.050000", operation_id=operation_id)

    assert segundo.resultado == primero.resultado
    assert len(entorno.auditorias_del_tope()) == 1


def test_inv06_el_mismo_operation_id_con_otro_tope_es_comando_inconsistente(
    entorno: Entorno,
) -> None:
    """Escenario "Mismo identificador con otro tope"."""
    vendedor = entorno.crear_rol("Vendedor")
    operation_id = uuid4()
    entorno.definir(vendedor.id, "0.050000", operation_id=operation_id)

    with pytest.raises(ComandoInconsistenteError):
        entorno.definir(vendedor.id, "0.200000", operation_id=operation_id)

    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0.050000")


def test_el_comando_no_se_acepta_sin_conexion(entorno: Entorno) -> None:
    """Escenario "El comando no se acepta sin conexión"."""
    vendedor = entorno.crear_rol("Vendedor")
    item = ItemLote(
        operation_id=uuid4(),
        tipo=DEFINIR,
        version=1,
        modo="OFFLINE",
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido={"rol_id": str(vendedor.id), "tope_descuento": "0.050000"},
    )

    (resultado,) = sync_service.procesar_lote(
        entorno.sesion,
        RELOJ,
        organizacion_id=entorno.org,
        usuario_id=entorno.usuario_id,
        dispositivo_id=entorno.dispositivo_id,
        items=[item],
    )

    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0")


def test_inv01_una_falla_despues_del_cambio_y_antes_de_la_auditoria_no_deja_nada(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    vendedor = entorno.crear_rol("Vendedor")

    def _falla(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("falla inyectada antes de la auditoría")

    monkeypatch.setattr(identidad_service, "registrar_auditoria", _falla)
    with pytest.raises(RuntimeError, match="falla inyectada"):
        entorno.definir(vendedor.id, "0.050000")
    monkeypatch.undo()

    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0")
    assert entorno.auditorias_del_tope() == []


# --- por HTTP (13.2) ----------------------------------------------------------------------------


def test_put_define_el_tope_y_devuelve_el_rol_con_el_tope_como_cadena(
    cliente: TestClient, entorno: Entorno
) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    vendedor = entorno.crear_rol("Vendedor/Repartidor", permisos=frozenset({DM}))

    respuesta = cliente.put(
        f"{URL_ROLES}/{vendedor.id}/tope-descuento",
        json={"tope_descuento": "0.050000"},
        headers=_con_op(administrador),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "id": str(vendedor.id),
        "nombre": "Vendedor/Repartidor",
        "activo": True,
        "tope_descuento": "0.050000",
    }
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0.050000")
    assert entorno.permisos_de(vendedor.id) == [DM]


def test_put_exige_operation_id(cliente: TestClient, entorno: Entorno) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    vendedor = entorno.crear_rol("Vendedor")

    respuesta = cliente.put(
        f"{URL_ROLES}/{vendedor.id}/tope-descuento",
        json={"tope_descuento": "0.050000"},
        headers=administrador,
    )

    assert respuesta.status_code == 400


def test_put_sin_admin_usuarios_responde_403_y_no_cambia(
    cliente: TestClient, entorno: Entorno
) -> None:
    supervisor = entorno.con_permisos(cliente, "GESTIONAR_DESCUENTOS")
    vendedor = entorno.crear_rol("Vendedor")

    respuesta = cliente.put(
        f"{URL_ROLES}/{vendedor.id}/tope-descuento",
        json={"tope_descuento": "0.050000"},
        headers=_con_op(supervisor),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0")


@pytest.mark.parametrize("tope", ["-0.01", "1.000001", "0.1234567"])
def test_put_con_tope_fuera_de_rango_responde_422_con_su_codigo(
    cliente: TestClient, entorno: Entorno, tope: str
) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    vendedor = entorno.crear_rol("Vendedor")

    respuesta = cliente.put(
        f"{URL_ROLES}/{vendedor.id}/tope-descuento",
        json={"tope_descuento": tope},
        headers=_con_op(administrador),
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["codigo"] == "IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO"
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0")


@pytest.mark.parametrize("valor", [0.05, 1, None])
def test_inv03_put_con_el_tope_como_numero_responde_422(
    cliente: TestClient, entorno: Entorno, valor: object
) -> None:
    """Escenario "El tope llega como número"."""
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    vendedor = entorno.crear_rol("Vendedor")

    respuesta = cliente.put(
        f"{URL_ROLES}/{vendedor.id}/tope-descuento",
        json={"tope_descuento": valor},
        headers=_con_op(administrador),
    )

    assert respuesta.status_code == 422
    assert entorno.rol(vendedor.id).tope_descuento == Decimal("0")


def test_inv21_put_sobre_un_rol_de_otra_organizacion_responde_404_sin_efectos(
    cliente: TestClient, entorno: Entorno, sesion: Session
) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    ajena = Entorno(sesion)
    rol_ajeno = ajena.crear_rol("Vendedor ajeno", "0.020000")

    respuesta = cliente.put(
        f"{URL_ROLES}/{rol_ajeno.id}/tope-descuento",
        json={"tope_descuento": "0.050000"},
        headers=_con_op(administrador),
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert ajena.rol_de(ajena.org, rol_ajeno.id).tope_descuento == Decimal("0.020000")


def test_inv21_un_cuerpo_con_organizacion_id_se_rechaza(
    cliente: TestClient, entorno: Entorno
) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    vendedor = entorno.crear_rol("Vendedor")

    respuesta = cliente.put(
        f"{URL_ROLES}/{vendedor.id}/tope-descuento",
        json={"tope_descuento": "0.050000", "organizacion_id": str(uuid4())},
        headers=_con_op(administrador),
    )

    assert respuesta.status_code == 422


def test_inv06_put_con_el_mismo_operation_id_devuelve_lo_mismo_y_con_otro_tope_409(
    cliente: TestClient, entorno: Entorno
) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    vendedor = entorno.crear_rol("Vendedor")
    url = f"{URL_ROLES}/{vendedor.id}/tope-descuento"
    operation_id = uuid4()

    primera = cliente.put(
        url, json={"tope_descuento": "0.050000"}, headers=_con_op(administrador, operation_id)
    )
    segunda = cliente.put(
        url, json={"tope_descuento": "0.050000"}, headers=_con_op(administrador, operation_id)
    )
    otra = cliente.put(
        url, json={"tope_descuento": "0.200000"}, headers=_con_op(administrador, operation_id)
    )

    assert primera.status_code == 200 and segunda.json() == primera.json()
    assert otra.status_code == 409
    assert otra.json()["codigo"] == "COMANDO_INCONSISTENTE"
    assert len(entorno.auditorias_del_tope()) == 1


def test_get_roles_lista_los_de_la_organizacion_con_el_tope_como_cadena(
    cliente: TestClient, entorno: Entorno, sesion: Session
) -> None:
    """Escenario "Consulta de roles con su tope": ningún rol de otra organización."""
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    entorno.crear_rol("Administrador", "1.000000")
    entorno.crear_rol("Vendedor/Repartidor", "0.050000")
    ajena = Entorno(sesion)
    ajena.crear_rol("Rol ajeno", "0.300000")

    respuesta = cliente.get(URL_ROLES, headers=administrador)

    assert respuesta.status_code == 200, respuesta.text
    por_nombre = {rol["nombre"]: rol for rol in respuesta.json()}
    assert por_nombre["Administrador"]["tope_descuento"] == "1.000000"
    assert por_nombre["Vendedor/Repartidor"]["tope_descuento"] == "0.050000"
    assert por_nombre["Vendedor/Repartidor"]["activo"] is True
    assert set(por_nombre["Vendedor/Repartidor"]) == {
        "id",
        "nombre",
        "activo",
        "tope_descuento",
        "permisos",
        "usuarios_activos",  # change 17b, 7.2 (aditivo)
    }
    assert "Rol ajeno" not in por_nombre


def test_get_roles_trae_los_permisos_de_cada_rol_en_orden_estable(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Decisión 2026-10-15: la lectura trae los permisos (lista de códigos, ordenada) para que la
    pantalla "Topes por rol" avise solo donde corresponde (DSC-06)."""
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    entorno.crear_rol(
        "Vendedor/Repartidor",
        "0.000000",
        permisos=frozenset({"DESCUENTO_MANUAL", "VER_COSTOS", "ADMIN_USUARIOS"}),
    )
    entorno.crear_rol("Sin permisos", "0.000000")

    respuesta = cliente.get(URL_ROLES, headers=administrador)

    assert respuesta.status_code == 200, respuesta.text
    por_nombre = {rol["nombre"]: rol for rol in respuesta.json()}
    assert por_nombre["Vendedor/Repartidor"]["permisos"] == [
        "ADMIN_USUARIOS",
        "DESCUENTO_MANUAL",
        "VER_COSTOS",
    ]
    assert por_nombre["Sin permisos"]["permisos"] == []
    # El rol del propio administrador trae exactamente los suyos.
    propio = next(r for r in respuesta.json() if r["nombre"].startswith("Rol "))
    assert propio["permisos"] == ["ADMIN_USUARIOS"]


def test_inv21_get_roles_no_mezcla_los_permisos_de_otra_organizacion(
    cliente: TestClient, entorno: Entorno, sesion: Session
) -> None:
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")
    entorno.crear_rol("Vendedor/Repartidor", "0.000000", permisos=frozenset({"VER_COSTOS"}))
    ajena = Entorno(sesion)
    ajena.crear_rol("Vendedor/Repartidor", "0.000000", permisos=frozenset({"DESCUENTO_MANUAL"}))

    respuesta = cliente.get(URL_ROLES, headers=administrador)

    por_nombre = {rol["nombre"]: rol for rol in respuesta.json()}
    assert por_nombre["Vendedor/Repartidor"]["permisos"] == ["VER_COSTOS"]
    assert "DESCUENTO_MANUAL" not in respuesta.text


def test_get_roles_resuelve_los_permisos_con_un_numero_fijo_de_consultas(
    cliente: TestClient, entorno: Entorno
) -> None:
    """Sin N+1: agregar roles no agrega consultas a `rol_permiso`."""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")

    def consultas_a_rol_permiso() -> int:
        contador = {"n": 0}

        def contar(_c, _cur, sentencia, *_a) -> None:  # type: ignore[no-untyped-def]
            if "FROM rol_permiso" in sentencia:
                contador["n"] += 1

        event.listen(Engine, "before_cursor_execute", contar)
        try:
            assert cliente.get(URL_ROLES, headers=administrador).status_code == 200
        finally:
            event.remove(Engine, "before_cursor_execute", contar)
        return contador["n"]

    antes = consultas_a_rol_permiso()
    for i in range(4):
        entorno.crear_rol(f"Extra {i}", permisos=frozenset({"VER_COSTOS"}))
    assert consultas_a_rol_permiso() == antes


def test_get_roles_sin_admin_usuarios_responde_403(cliente: TestClient, entorno: Entorno) -> None:
    supervisor = entorno.con_permisos(cliente, "GESTIONAR_DESCUENTOS")

    respuesta = cliente.get(URL_ROLES, headers=supervisor)

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"


def test_get_yo_sigue_sin_exponer_el_tope(cliente: TestClient, entorno: Entorno) -> None:
    """Escenario "La sesión en curso sigue sin exponer el tope" (ADR-027, SYN-11)."""
    administrador = entorno.con_permisos(cliente, "ADMIN_USUARIOS")

    respuesta = cliente.get("/api/v1/yo", headers=administrador)

    assert respuesta.status_code == 200
    assert "tope" not in respuesta.text
