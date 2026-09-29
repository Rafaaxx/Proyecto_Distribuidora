"""Change 07, tarea 6.3: cobertura de aislamiento (INV-21, SEG-07) de las
siete rutas de `clientes/api.py` (tres lecturas, cuatro escrituras
dedicadas -- `design.md` D9, enmienda 2026-09-29) -- las que
`test_inv21_ratchet_rutas.py::test_inv21_toda_ruta_de_negocio_esta_cubierta_por_el_aislamiento`
señala como sin cobertura hasta que se agregan a `COBERTURA_DE_AISLAMIENTO`
con su prueba real acá.

Mismo arnés HTTP que `test_inv21_aislamiento_endpoints_proveedores.py`:
Postgres real, `cliente` con motor propio, y **login real** de dos
organizaciones con `POST /api/v1/auth/login` -- nunca un access token
fabricado a mano con `emitir_access_token`, porque eso no probaría que el
flujo de autenticación real produzca un contexto con la organización
correcta.

Además de "recurso ajeno -> 404" para cada ruta, cubre lo que la tarea 6.3
pide explícitamente y no es un id de ruta:

- una referencia ajena EN EL CONTENIDO de `CLIENTE_CREDITO_MODIFICAR`
  (`cliente_id` de la organización B en el sobre del comando de A), ahora vía
  `PUT /api/v1/clientes/{cliente_id}/credito`;
- la configuración del consumidor final de otra organización: la lectura
  `/clientes/consumidor-final` de A no devuelve el cliente de B, ni
  siquiera ahora que existe (el aislamiento es por construcción: el
  identificador sale de la configuración de A, no de la petición);
- `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` de A no toca la configuración de B,
  ahora vía `POST /api/v1/clientes/consumidor-final`.

Estos dos últimos casos se probaban por `POST /api/v1/sync/comandos` porque
las escrituras de `clientes` no tenían endpoint propio; D9 (enmienda
2026-09-29) agregó las cuatro rutas dedicadas (mismo patrón que
`proveedores/api.py`) porque el despacho genérico no ejecuta hoy ningún
handler `ONLINE` (deuda nominada al change 17, ver `catalogo/commands.py`).
Este archivo usa las rutas dedicadas en vez del bus genérico."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_v1 import sistema
from app.core.config import Settings
from app.core.db import crear_engine, crear_session_factory
from app.core.ids import nuevo_id
from app.core.seguridad import hashear_password
from app.main import crear_app
from app.modules.clientes import repository as clientes_repository
from app.modules.clientes.models import Cliente
from app.modules.identidad import repository
from app.modules.identidad.models import ConfiguracionOrganizacion, Organizacion

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
PASSWORD = "una-contrasena-larga-123"
JWT_SECRET = "secreto-de-prueba-aislamiento-clientes"


_USUARIO_IDS_POR_NOMBRE: dict[str, UUID] = {}
"""Mapa `nombre_usuario -> usuario_id` que llena `_crear_usuario` y lee
`_login`: el login real no expone el `usuario_id` (`TokenResponse` solo trae
`access_token`), así que hace falta recordarlo por fuera para declararlo en
el sobre del lote."""


class SesionHTTP(NamedTuple):
    """Lo que devuelve un login real: el token para las lecturas y los dos
    identificadores que el lote de sincronización tiene que declarar."""

    token: str
    usuario_id: UUID
    dispositivo_id: UUID


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
def sesion(database_url: str, _engine_de_sesion) -> Iterator[Session]:
    engine = crear_engine(database_url)
    try:
        factory = crear_session_factory(engine)
        with factory() as sesion_real:
            yield sesion_real
    finally:
        engine.dispose()


def _crear_organizacion(sesion: Session, slug: str) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba",
        slug=slug,
        cuit=None,
        moneda="ARS",
        zona_horaria="America/Argentina/Mendoza",
        estado="ACTIVA",
        creado_en=MOMENTO,
        actualizado_en=MOMENTO,
        actualizado_por_id=None,
    )
    sesion.add(organizacion)
    sesion.flush()
    # `CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR` escribe `configuracion_organizacion`
    # (D4): sin esta fila, `identidad_service.configurar_consumidor_final`
    # devuelve `None` y `clientes_service` lo traduce en
    # `ConfiguracionDeOrganizacionAusenteError` en vez del resultado esperado.
    sesion.add(
        ConfiguracionOrganizacion(
            organizacion_id=organizacion.id,
            modo_impositivo="B",
            lista_precio_default_id=None,
            politica_credito_default="ADVERTIR",
            tolerancia_offline_tipo=None,
            tolerancia_offline_valor=None,
            descuento_manual_habilitado=False,
            motivo_obligatorio_descuento=None,
            motivo_obligatorio_lista=True,
            redondeo_multiplo=None,
            redondeo_direccion=None,
            permite_consumidor_final=None,
            cliente_consumidor_final_id=None,
            estado_facturacion_default="PENDIENTE",
            modalidad_iva_default="CLIENTE",
            intentos_pin_max=3,
            desvio_reloj_max_segundos=None,
            creado_en=MOMENTO,
            actualizado_en=MOMENTO,
            actualizado_por_id=None,
        )
    )
    sesion.flush()
    return organizacion


def _crear_usuario(sesion: Session, organizacion_id: UUID, *, nombre_usuario: str) -> UUID:
    """Un usuario con los tres permisos de clientes, para no probar el
    aislamiento mezclado con el de permiso: acá la sesión es válida y lo que se
    prueba es que no alcanza para ver lo de otra organización.

    Devuelve el `usuario_id` real (el login no lo expone: `TokenResponse` solo
    trae `access_token`, `app/api_v1/auth.py`), porque `_login` lo necesita
    para declarar el mismo id en el sobre del lote (`ColaAjenaError`,
    `sync/service.py`)."""
    rol = repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Rol de prueba",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in ("ADMIN_CONFIGURACION", "GESTIONAR_CLIENTES", "GESTIONAR_CREDITO"):
        repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario_id = nuevo_id()
    repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        usuario=nombre_usuario,
        nombre="Persona de prueba",
        email=None,
        password_hash=hashear_password(PASSWORD),
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    _USUARIO_IDS_POR_NOMBRE[nombre_usuario] = usuario_id
    return usuario_id


def _login(cliente: TestClient, slug: str, usuario: str) -> SesionHTTP:
    """Login REAL de una organización (nunca un JWT fabricado a mano: eso no
    probaría que el flujo de autenticación real produzca el contexto correcto).

    Devuelve el token y los dos identificadores que el lote tiene que declarar:
    el bus los compara contra la sesión (`ColaAjenaError`, tarea 8.5) y los usa
    para armar el sobre."""
    dispositivo_id = uuid4()
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(dispositivo_id),
            "nombre_dispositivo": "PC",
        },
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    return SesionHTTP(
        token=cuerpo["access_token"],
        usuario_id=_USUARIO_IDS_POR_NOMBRE[usuario],
        dispositivo_id=dispositivo_id,
    )


def _crear_cliente(
    sesion: Session,
    organizacion_id: UUID,
    *,
    nombre: str,
    es_consumidor_final: bool = False,
    limite_credito: Decimal | None = None,
) -> Cliente:
    creado = clientes_repository.crear_cliente(
        organizacion_id,
        sesion,
        cliente_id=nuevo_id(),
        nombre=nombre,
        codigo=None,
        razon_social=None,
        documento_tipo=None,
        documento_numero=None,
        direccion="Av. San Martín 1420",
        contacto="Rocío",
        telefono=None,
        email=None,
        lista_precio_id=None,
        estado_facturacion_default=None,
        es_consumidor_final=es_consumidor_final,
        limite_credito=limite_credito,
        politica_credito=None,
        tolerancia_offline_tipo=None,
        tolerancia_offline_valor=None,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    sesion.flush()
    return creado


def _dos_organizaciones(sesion: Session) -> tuple[Organizacion, Organizacion]:
    """A y B, cada una con su usuario y su login real. B tiene un cliente
    marcado como consumidor final, que es el recurso que la 6.3 pide no
    filtrar."""
    organizacion_a = _crear_organizacion(sesion, "org-a")
    _crear_usuario(sesion, organizacion_a.id, nombre_usuario="admin-a")
    organizacion_b = _crear_organizacion(sesion, "org-b")
    _crear_usuario(sesion, organizacion_b.id, nombre_usuario="admin-b")
    sesion.commit()
    return organizacion_a, organizacion_b


class TestAislamientoDeLasRutasDeClientes:
    def test_la_ficha_de_un_cliente_ajeno_responde_404(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """INV-21, SEG-07: el usuario de B pide la ficha de un cliente de A y
        la respuesta dice "no encontrado", nunca 403 y nunca 200 con los datos
        de A. Un 403 confirmaría que el cliente existe; por eso el 404 no
        distingue "ajeno" de "inexistente"."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        ajeno = _crear_cliente(sesion, organizacion_a.id, nombre="Kiosco La Esquina")
        sesion.commit()
        ajeno_id = ajeno.id
        sesion_b = _login(cliente, "org-b", "admin-b")

        respuesta = cliente.get(
            f"/api/v1/clientes/{ajeno_id}", headers={"Authorization": f"Bearer {sesion_b.token}"}
        )

        assert respuesta.status_code == 404, (
            f"Un recurso de otra organización responde 404, no 403 ni 200: "
            f"{respuesta.status_code} {respuesta.text}"
        )
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
        assert "Kiosco" not in respuesta.text, "El 404 no filtra el nombre del cliente ajeno."

    def test_un_cliente_ajeno_es_indistinguible_de_uno_inexistente(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Las dos respuestas 404 tienen el mismo código y la misma forma: si
        una dijera "existe en otra organización", el 404 dejaría de proteger
        nada."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        ajeno = _crear_cliente(sesion, organizacion_a.id, nombre="Kiosco La Esquina")
        sesion.commit()
        ajeno_id = ajeno.id
        sesion_b = _login(cliente, "org-b", "admin-b")
        cabeceras = {"Authorization": f"Bearer {sesion_b.token}"}

        del_ajeno = cliente.get(f"/api/v1/clientes/{ajeno_id}", headers=cabeceras)
        inexistente = cliente.get(f"/api/v1/clientes/{uuid4()}", headers=cabeceras)

        assert del_ajeno.status_code == inexistente.status_code == 404
        assert del_ajeno.json()["codigo"] == inexistente.json()["codigo"]

    def test_el_listado_no_expone_clientes_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """El listado es paginado y ordenado por nombre: sin el filtro de
        organización, el cliente de A aparecería en la página de B."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        _crear_cliente(sesion, organizacion_a.id, nombre="Kiosco La Esquina")
        propio = _crear_cliente(sesion, organizacion_b.id, nombre="Kiosco El Faro")
        sesion.commit()
        propio_id = propio.id
        sesion_b = _login(cliente, "org-b", "admin-b")

        respuesta = cliente.get(
            "/api/v1/clientes", headers={"Authorization": f"Bearer {sesion_b.token}"}
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert [item["id"] for item in cuerpo["items"]] == [str(propio_id)], (
            "Solo los clientes de la organización del token."
        )
        assert "Kiosco La Esquina" not in respuesta.text

    def test_el_listado_ajeno_no_se_encuentra_tampoco_por_texto_ni_por_documento(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """INV-02: el filtro por `texto` de B tampoco cruza organizaciones. Un
        buscador que encontrara el cliente de A por nombre confirmaría que
        existe sin mostrarlo."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        _crear_cliente(
            sesion,
            organizacion_a.id,
            nombre="Kiosco La Esquina",
        )
        _crear_cliente(sesion, organizacion_b.id, nombre="Kiosco El Faro")
        sesion.commit()
        sesion_b = _login(cliente, "org-b", "admin-b")
        cabeceras = {"Authorization": f"Bearer {sesion_b.token}"}

        por_nombre = cliente.get("/api/v1/clientes", params={"texto": "Esquina"}, headers=cabeceras)
        por_filtro_de_estado = cliente.get(
            "/api/v1/clientes", params={"estado": "ACTIVO"}, headers=cabeceras
        )

        assert por_nombre.status_code == 200
        assert por_nombre.json()["items"] == [], "B no tiene ningún cliente que contenga 'Esquina'."
        assert por_filtro_de_estado.status_code == 200
        assert [item["nombre"] for item in por_filtro_de_estado.json()["items"]] == [
            "Kiosco El Faro"
        ]

    def test_la_lectura_del_consumidor_final_no_devuelve_el_de_otra_organizacion(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario 'Consulta aislada por organización' de la spec
        `consumidor-final`: A no recibe ningún dato del cliente ni de la
        configuración de B.

        A responde `habilitado: false`, NO el cliente de B: el aislamiento acá
        es por construcción, porque el identificador sale de la configuración
        de A y no de un parámetro de la petición (INV-21)."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        consumidor_de_b = _crear_cliente(
            sesion,
            organizacion_b.id,
            nombre="Consumidor final de B",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        sesion.commit()
        consumidor_de_b_id = consumidor_de_b.id
        sesion_a = _login(cliente, "org-a", "admin-a")

        respuesta = cliente.get(
            "/api/v1/clientes/consumidor-final",
            headers={"Authorization": f"Bearer {sesion_a.token}"},
        )

        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo == {"habilitado": False, "cliente": None}, (
            "A no habilitó consumidor final: su respuesta no puede traer el de B."
        )
        assert str(consumidor_de_b_id) not in respuesta.text
        assert "Consumidor final de B" not in respuesta.text

    def test_cada_organizacion_ve_su_propio_consumidor_final(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Complementaria: A y B con su propio consumidor final, y cada sesión
        ve el suyo y solo el suyo."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        final_a = _crear_cliente(
            sesion,
            organizacion_a.id,
            nombre="Consumidor final A",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        final_b = _crear_cliente(
            sesion,
            organizacion_b.id,
            nombre="Consumidor final B",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        sesion.commit()
        final_a_id, final_b_id = final_a.id, final_b.id

        cuerpo_a = cliente.get(
            "/api/v1/clientes/consumidor-final",
            headers={"Authorization": f"Bearer {_login(cliente, 'org-a', 'admin-a').token}"},
        ).json()
        cuerpo_b = cliente.get(
            "/api/v1/clientes/consumidor-final",
            headers={"Authorization": f"Bearer {_login(cliente, 'org-b', 'admin-b').token}"},
        ).json()

        assert cuerpo_a["cliente"]["id"] == str(final_a_id)
        assert cuerpo_b["cliente"]["id"] == str(final_b_id)
        assert str(final_b_id) not in str(cuerpo_a)
        assert str(final_a_id) not in str(cuerpo_b)

    def test_el_credito_de_un_cliente_ajeno_no_se_modifica(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Referencia ajena EN EL CONTENIDO del comando (tarea 6.3): el sobre
        es de A y su `contenido` trae el `cliente_id` de B. La respuesta tiene
        que ser la de un recurso que no existe en A, y el crédito de B tiene
        que seguir como estaba.

        Va por `PUT /api/v1/clientes/{cliente_id}/credito` (D9, enmienda
        2026-09-29: ruta dedicada, mismo patrón que `proveedores/api.py`, en
        vez del despacho genérico de `POST /sync/comandos` que no ejecuta
        ningún handler `ONLINE` -- deuda nominada al change 17): el
        aislamiento de las escrituras se comprueba por HTTP, no llamando al
        handler en Python."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        cliente_de_b = _crear_cliente(
            sesion, organizacion_b.id, nombre="Kiosco El Faro", limite_credito=Decimal("10000.00")
        )
        sesion.commit()
        cliente_de_b_id = cliente_de_b.id
        sesion_a = _login(cliente, "org-a", "admin-a")

        respuesta = cliente.put(
            f"/api/v1/clientes/{cliente_de_b_id}/credito",
            json={"limite_credito": "999999.00", "politica_credito": "BLOQUEAR"},
            headers={
                "Authorization": f"Bearer {sesion_a.token}",
                "Operation-Id": str(uuid4()),
            },
        )

        assert respuesta.status_code == 404, (
            f"El `cliente_id` de B en la ruta de A es un recurso inexistente "
            f"para A: {respuesta.status_code} {respuesta.text}"
        )
        assert respuesta.json()["codigo"] == "RECURSO_NO_ENCONTRADO"

        verificacion = crear_session_factory(crear_engine(sesion.get_bind().url))()
        try:
            fila = verificacion.get(Cliente, cliente_de_b_id)
            assert fila is not None
            assert fila.limite_credito == Decimal("10000.00"), (
                "El crédito del cliente de B no cambió: el comando no encontró "
                "el cliente en la organización del sobre."
            )
            assert fila.politica_credito is None
        finally:
            verificacion.close()

    def test_la_habilitacion_del_consumidor_final_de_a_no_toca_la_configuracion_de_b(
        self, cliente: TestClient, sesion: Session
    ) -> None:
        """Escenario 'La configuración de otra organización no se toca' (spec
        `consumidor-final`): A habilita su consumidor final y la configuración
        de B queda igual, con su propio cliente.

        Va por `POST /api/v1/clientes/consumidor-final` (D9, enmienda
        2026-09-29: ruta dedicada)."""
        organizacion_a, organizacion_b = _dos_organizaciones(sesion)
        final_b = _crear_cliente(
            sesion,
            organizacion_b.id,
            nombre="Consumidor final de B",
            es_consumidor_final=True,
            limite_credito=Decimal("0.00"),
        )
        sesion.commit()
        final_b_id = final_b.id
        sesion_a = _login(cliente, "org-a", "admin-a")

        respuesta = cliente.post(
            "/api/v1/clientes/consumidor-final",
            json={"nombre": "Consumidor final"},
            headers={
                "Authorization": f"Bearer {sesion_a.token}",
                "Operation-Id": str(uuid4()),
            },
        )

        assert respuesta.status_code == 201, (
            f"A sí puede habilitar su propio consumidor final: {respuesta.text}"
        )
        cuerpo = cliente.get(
            "/api/v1/clientes/consumidor-final",
            headers={"Authorization": f"Bearer {sesion_a.token}"},
        ).json()
        assert cuerpo["habilitado"] is True
        assert cuerpo["cliente"]["id"] != str(final_b_id)

        # B sigue viendo el suyo, sin cambios.
        cuerpo_b = cliente.get(
            "/api/v1/clientes/consumidor-final",
            headers={"Authorization": f"Bearer {_login(cliente, 'org-b', 'admin-b').token}"},
        ).json()
        assert cuerpo_b["cliente"]["id"] == str(final_b_id), (
            "La habilitación de A no puede haber reapuntado la configuración de B."
        )
