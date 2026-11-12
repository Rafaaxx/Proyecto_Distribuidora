"""Tareas 3.1 y 3.2 (change 20c; `design.md` D1, D2, D3, D4, D13): `MOTIVO_CREAR` y
`MOTIVO_MODIFICAR` por `POST` y `PUT /api/v1/configuracion/motivos`.

Mismo arnés que `test_medio_pago_comandos.py`: PostgreSQL real, motor propio de la aplicación y
`login` real. Reglas citadas: TR-09, TR-06, CAT-05, STK-08, RUT-09, INV-02, INV-06, INV-21,
INV-01 y ADR-061.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import medios_pago_utiles as utiles
import pytest
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from medios_pago_utiles import Entorno, con_op
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_motivo_sql

from app.core.clock import FixedClock
from app.modules.configuracion import service as configuracion_service
from app.modules.stock.domain.errores import MotivoInvalidoError
from app.modules.stock.domain.operaciones import validar_motivo_de_ajuste
from app.modules.sync import service as sync_service
from app.modules.sync.service import ItemLote

URL_MOTIVOS = "/api/v1/configuracion/motivos"

# Las fixtures viven en `medios_pago_utiles.py`; se enlazan por asignación (no por `import`).
_limpiar_datos_confirmados = utiles._limpiar_datos_confirmados
cliente_http = utiles.cliente_http
sesion = utiles.sesion


def _crear_motivo(
    entorno: Entorno, ambito: str, nombre: str, *, activo: bool = True, org: UUID | None = None
) -> UUID:
    motivo_id = crear_motivo_sql(
        entorno.sesion, org or entorno.org, ambito=ambito, nombre=nombre, activo=activo
    )
    entorno.sesion.commit()
    return motivo_id


def _filas(entorno: Entorno, ambito: str | None = None) -> list[dict[str, Any]]:
    entorno.sesion.rollback()
    consulta = "SELECT id, ambito, nombre, activo FROM motivo WHERE organizacion_id = :o"
    parametros: dict[str, object] = {"o": entorno.org}
    if ambito is not None:
        consulta += " AND ambito = :a"
        parametros["a"] = ambito
    filas = entorno.sesion.execute(text(consulta + " ORDER BY nombre"), parametros).mappings()
    return [dict(f) for f in filas]


def _auditoria(entorno: Entorno, accion: str) -> list[dict[str, Any]]:
    return entorno.auditoria_de(accion, entidad="motivo")


def _cuerpo(**cambios: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {"ambito": "AJUSTE_STOCK", "nombre": "Robo"}
    cuerpo.update(cambios)
    return cuerpo


# ======================= MOTIVO_CREAR (3.1) ===========================================


class TestMotivoCrear:
    def test_crea_un_motivo_activo_con_el_nombre_recortado_y_lo_devuelve(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(nombre="  Robo "), headers=con_op(headers)
        )

        assert respuesta.status_code == 201, respuesta.text
        cuerpo = respuesta.json()
        UUID(cuerpo["id"])
        assert (cuerpo["ambito"], cuerpo["nombre"], cuerpo["activo"]) == (
            "AJUSTE_STOCK",
            "Robo",
            True,
        )
        assert cuerpo["actualizado_en"]
        assert "organizacion_id" not in cuerpo
        assert [f["nombre"] for f in _filas(entorno)] == ["Robo"]

    @pytest.mark.parametrize("nombre", ["", "   ", "\t"])
    def test_un_nombre_vacio_es_nombre_invalido_422(
        self, cliente_http: TestClient, sesion: Session, nombre: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(nombre=nombre), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "NOMBRE_INVALIDO"
        assert _filas(entorno) == []

    @pytest.mark.parametrize("ambito", ["OTRO_AMBITO", "", "ajuste_stock"])
    def test_un_ambito_fuera_de_la_lista_es_ambito_invalido_422(
        self, cliente_http: TestClient, sesion: Session, ambito: str
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(ambito=ambito), headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "AMBITO_INVALIDO"
        assert _filas(entorno) == []

    @pytest.mark.parametrize("repetido", ["Rotura", "rotura", " ROTURA "])
    def test_inv02_un_nombre_repetido_en_el_ambito_es_409_sin_distinguir_mayusculas(
        self, cliente_http: TestClient, sesion: Session, repetido: str
    ) -> None:
        entorno = Entorno(sesion)
        _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(nombre=repetido), headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"
        assert len(_filas(entorno)) == 1

    def test_un_nombre_repetido_tambien_contra_un_motivo_de_baja(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura", activo=False)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(nombre="rotura"), headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"

    def test_inv02_el_mismo_nombre_en_otro_ambito_o_en_otra_organizacion_se_acepta(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        una = Entorno(sesion)
        otra = Entorno(sesion)
        headers_una = una.entrar(cliente_http)
        headers_otra = otra.entrar(cliente_http)

        en_ajuste = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(nombre="Otro"), headers=con_op(headers_una)
        )
        en_anulacion = cliente_http.post(
            URL_MOTIVOS,
            json=_cuerpo(ambito="ANULACION_VENTA", nombre="Otro"),
            headers=con_op(headers_una),
        )
        en_otra_org = cliente_http.post(
            URL_MOTIVOS, json=_cuerpo(nombre="Otro"), headers=con_op(headers_otra)
        )

        assert en_ajuste.status_code == en_anulacion.status_code == en_otra_org.status_code == 201

    def test_sin_admin_configuracion_responde_403_sin_efectos_ni_reserva(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http, "cobrador1")

        respuesta = cliente_http.post(URL_MOTIVOS, json=_cuerpo(), headers=con_op(headers))

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _filas(entorno) == []
        assert entorno.contar_comandos("MOTIVO_CREAR") == 0

    def test_inv06_reenviar_el_mismo_operation_id_no_duplica(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))

        primera = cliente_http.post(URL_MOTIVOS, json=_cuerpo(), headers=headers)
        segunda = cliente_http.post(URL_MOTIVOS, json=_cuerpo(), headers=headers)

        assert primera.status_code == segunda.status_code == 201
        assert primera.json()["id"] == segunda.json()["id"]
        assert len(_filas(entorno)) == 1
        assert len(_auditoria(entorno, "MOTIVO_CREAR")) == 1

    @pytest.mark.parametrize("cambios", [{"organizacion_id": str(uuid4())}, {"nombre": 7}])
    def test_un_cuerpo_malformado_se_rechaza_con_422(
        self, cliente_http: TestClient, sesion: Session, cambios: dict[str, object]
    ) -> None:
        entorno = Entorno(sesion)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.post(URL_MOTIVOS, json=_cuerpo(**cambios), headers=con_op(headers))

        assert respuesta.status_code == 422
        assert _filas(entorno) == []

    def test_deja_una_fila_de_auditoria_con_el_estado_despues(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # D13, AUD-01: "cambios de configuración" con `despues`.
        entorno = Entorno(sesion)
        headers = con_op(entorno.entrar(cliente_http))

        creado = cliente_http.post(URL_MOTIVOS, json=_cuerpo(), headers=headers).json()

        filas = _auditoria(entorno, "MOTIVO_CREAR")
        assert len(filas) == 1
        fila = filas[0]
        assert str(fila["entidad_id"]) == creado["id"]
        assert fila["antes"] is None
        assert fila["despues"] == {"ambito": "AJUSTE_STOCK", "nombre": "Robo", "activo": True}
        assert fila["usuario_id"] == entorno.usuarios["admin1"]
        assert str(fila["operation_id"]) == headers["Operation-Id"]
        assert fila["origen"] == "COMANDO"


# ======================= MOTIVO_MODIFICAR (3.2) =======================================


def _url(motivo_id: UUID) -> str:
    return f"{URL_MOTIVOS}/{motivo_id}"


class TestMotivoModificar:
    def test_renombra_el_motivo_conservando_su_id_y_su_ambito(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # CAT-05: las operaciones guardan el id, así que una anterior muestra el nombre nuevo.
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(motivo),
            json={"nombre": "  Rotura grave ", "activo": True},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["id"] == str(motivo)
        assert respuesta.json()["nombre"] == "Rotura grave"
        assert respuesta.json()["ambito"] == "AJUSTE_STOCK"
        assert [(f["id"], f["nombre"]) for f in _filas(entorno)] == [(motivo, "Rotura grave")]

    def test_un_campo_ambito_se_rechaza_y_el_ambito_no_cambia(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(motivo),
            json={"nombre": "Rotura", "activo": True, "ambito": "ANULACION_VENTA"},
            headers=con_op(headers),
        )

        assert respuesta.status_code == 422
        assert _filas(entorno)[0]["ambito"] == "AJUSTE_STOCK"

    def test_renombrar_a_un_nombre_ajeno_del_ambito_es_nombre_duplicado_409(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        _crear_motivo(entorno, "AJUSTE_STOCK", "Merma")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(motivo), json={"nombre": "MERMA", "activo": True}, headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "NOMBRE_DUPLICADO"
        assert "Rotura" in [f["nombre"] for f in _filas(entorno)]

    def test_renombrar_a_un_nombre_de_otro_ambito_o_cambiar_mayusculas_se_acepta(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        _crear_motivo(entorno, "ANULACION_VENTA", "Error de carga")
        headers = entorno.entrar(cliente_http)

        a_otro_ambito = cliente_http.put(
            _url(motivo), json={"nombre": "Error de carga", "activo": True}, headers=con_op(headers)
        )
        mayusculas = cliente_http.put(
            _url(motivo), json={"nombre": "ERROR DE CARGA", "activo": True}, headers=con_op(headers)
        )

        assert a_otro_ambito.status_code == mayusculas.status_code == 200

    def test_nombre_vacio_es_nombre_invalido_422(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(motivo), json={"nombre": "  ", "activo": True}, headers=con_op(headers)
        )

        assert respuesta.status_code == 422
        assert respuesta.json()["codigo"] == "NOMBRE_INVALIDO"

    def test_la_baja_saca_el_motivo_del_listado_por_ambito_y_de_los_ajustes_nuevos(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # CAT-05, TR-06, STK-08: deja de ofrecerse y de aceptarse; no se borra y se lee por id.
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        _crear_motivo(entorno, "AJUSTE_STOCK", "Merma")
        headers = entorno.entrar(cliente_http)

        baja = cliente_http.put(
            _url(motivo), json={"nombre": "Rotura", "activo": False}, headers=con_op(headers)
        )
        listado = cliente_http.get(f"{URL_MOTIVOS}?ambito=AJUSTE_STOCK", headers=headers)

        assert baja.status_code == 200
        assert baja.json()["activo"] is False
        assert [m["nombre"] for m in listado.json()["items"]] == ["Merma"]
        entorno.sesion.rollback()
        leido = configuracion_service.obtener_motivo(entorno.org, motivo, entorno.sesion)
        assert leido is not None
        with pytest.raises(MotivoInvalidoError):
            validar_motivo_de_ajuste(activo=leido.activo, ambito=leido.ambito)

    def test_reactivar_vuelve_a_ofrecerlo(self, cliente_http: TestClient, sesion: Session) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura", activo=False)
        _crear_motivo(entorno, "AJUSTE_STOCK", "Merma")
        headers = entorno.entrar(cliente_http)

        alta = cliente_http.put(
            _url(motivo), json={"nombre": "Rotura", "activo": True}, headers=con_op(headers)
        )
        listado = cliente_http.get(f"{URL_MOTIVOS}?ambito=AJUSTE_STOCK", headers=headers)

        assert alta.status_code == 200
        assert [m["nombre"] for m in listado.json()["items"]] == ["Merma", "Rotura"]

    def test_dar_de_baja_el_ultimo_motivo_activo_del_ambito_es_409(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        unico = _crear_motivo(entorno, "LIBERACION_JORNADA", "Faltante")
        _crear_motivo(entorno, "LIBERACION_JORNADA", "Viejo", activo=False)
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(unico), json={"nombre": "Faltante", "activo": False}, headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "ULTIMO_MOTIVO_ACTIVO"
        assert _filas(entorno, "LIBERACION_JORNADA")[0]["activo"] is True

    def test_el_ultimo_motivo_de_un_ambito_no_depende_de_los_de_otro_ambito(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        unico = _crear_motivo(entorno, "LIBERACION_JORNADA", "Faltante")
        _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http)

        respuesta = cliente_http.put(
            _url(unico), json={"nombre": "Faltante", "activo": False}, headers=con_op(headers)
        )

        assert respuesta.status_code == 409
        assert respuesta.json()["codigo"] == "ULTIMO_MOTIVO_ACTIVO"

    def test_un_motivo_ajeno_o_inexistente_es_404(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        # INV-21: otra organización responde 404, nunca 403.
        una = Entorno(sesion)
        otra = Entorno(sesion)
        de_otra = _crear_motivo(otra, "AJUSTE_STOCK", "Rotura")
        headers = una.entrar(cliente_http)

        ajeno = cliente_http.put(
            _url(de_otra), json={"nombre": "X", "activo": True}, headers=con_op(headers)
        )
        inexistente = cliente_http.put(
            _url(uuid4()), json={"nombre": "X", "activo": True}, headers=con_op(headers)
        )

        assert ajeno.status_code == inexistente.status_code == 404
        assert _filas(otra)[0]["nombre"] == "Rotura"

    def test_sin_admin_configuracion_responde_403(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = entorno.entrar(cliente_http, "cobrador1")

        respuesta = cliente_http.put(
            _url(motivo), json={"nombre": "X", "activo": True}, headers=con_op(headers)
        )

        assert respuesta.status_code == 403
        assert respuesta.json()["codigo"] == "PERMISO_REQUERIDO"
        assert _filas(entorno)[0]["nombre"] == "Rotura"

    def test_inv06_reenviar_el_mismo_operation_id_aplica_una_sola_vez(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        headers = con_op(entorno.entrar(cliente_http))
        cuerpo = {"nombre": "Rotura grave", "activo": True}

        primera = cliente_http.put(_url(motivo), json=cuerpo, headers=headers)
        segunda = cliente_http.put(_url(motivo), json=cuerpo, headers=headers)

        assert primera.status_code == segunda.status_code == 200
        assert len(_auditoria(entorno, "MOTIVO_MODIFICAR")) == 1

    def test_deja_una_fila_de_auditoria_con_antes_y_despues(
        self, cliente_http: TestClient, sesion: Session
    ) -> None:
        entorno = Entorno(sesion)
        motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
        _crear_motivo(entorno, "AJUSTE_STOCK", "Merma")
        headers = con_op(entorno.entrar(cliente_http))

        cliente_http.put(_url(motivo), json={"nombre": "Rotura", "activo": False}, headers=headers)

        filas = _auditoria(entorno, "MOTIVO_MODIFICAR")
        assert len(filas) == 1
        assert filas[0]["antes"] == {"ambito": "AJUSTE_STOCK", "nombre": "Rotura", "activo": True}
        assert filas[0]["despues"] == {
            "ambito": "AJUSTE_STOCK",
            "nombre": "Rotura",
            "activo": False,
        }
        assert filas[0]["usuario_id"] == entorno.usuarios["admin1"]


# ======================= catálogo y lote del bus (3.4) ================================

MOMENTO_LOTE = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("tipo", ["MOTIVO_CREAR", "MOTIVO_MODIFICAR"])
def test_los_dos_tipos_estan_declarados_solo_online(tipo: str) -> None:
    # `02` §6.5, ADR-056: un maestro de configuración no se escribe sin conexión.
    import app.main  # noqa: F401  (puebla el catálogo real)
    from app.commands.catalogo import tipo_declarado

    declarado = tipo_declarado(tipo)

    assert declarado is not None
    assert (declarado.admite_online, declarado.admite_offline) == (True, False)
    assert declarado.permisos == ("ADMIN_CONFIGURACION",)


def _item_de_lote(
    entorno: Entorno,
    tipo: str,
    modo: str,
    contenido: dict[str, object],
    *,
    con_permiso: bool = True,
) -> tuple[ItemLote, UUID, UUID]:
    permisos = frozenset({"ADMIN_CONFIGURACION"}) if con_permiso else frozenset[str]()
    usuario_id, dispositivo_id = crear_usuario_y_dispositivo(
        entorno.sesion, entorno.org, permisos=permisos
    )
    entorno.sesion.commit()
    return (
        ItemLote(
            operation_id=uuid4(),
            tipo=tipo,
            version=1,
            modo=modo,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            occurred_at=MOMENTO_LOTE,
            secuencia=1,
            app_version="1.0.0",
            contenido=contenido,  # type: ignore[arg-type]
        ),
        usuario_id,
        dispositivo_id,
    )


def _procesar(
    sesion: Session, entorno: Entorno, item: ItemLote, usuario_id: UUID, dispositivo_id: UUID
) -> Any:
    (resultado,) = sync_service.procesar_lote(
        sesion,
        FixedClock(MOMENTO_LOTE),
        organizacion_id=entorno.org,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        items=[item],
    )
    return resultado


@pytest.mark.parametrize("tipo", ["MOTIVO_CREAR", "MOTIVO_MODIFICAR"])
def test_el_lote_rechaza_los_comandos_de_motivos_enviados_sin_conexion(
    sesion: Session, tipo: str
) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"ambito": "AJUSTE_STOCK", "nombre": "Robo"}
    item, usuario_id, dispositivo_id = _item_de_lote(entorno, tipo, "OFFLINE", contenido)

    resultado = _procesar(sesion, entorno, item, usuario_id, dispositivo_id)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "MODO_NO_ADMITIDO_PARA_TIPO"
    assert _filas(entorno) == []


def test_por_el_lote_en_modo_online_se_comporta_igual_que_por_rest(sesion: Session) -> None:
    entorno = Entorno(sesion)
    contenido: dict[str, object] = {"ambito": "AJUSTE_STOCK", "nombre": "Robo"}
    item, usuario_id, dispositivo_id = _item_de_lote(entorno, "MOTIVO_CREAR", "ONLINE", contenido)

    resultado = _procesar(sesion, entorno, item, usuario_id, dispositivo_id)

    assert resultado.estado == "ACEPTADO", resultado
    assert [(f["ambito"], f["nombre"], f["activo"]) for f in _filas(entorno)] == [
        ("AJUSTE_STOCK", "Robo", True)
    ]
    assert len(_auditoria(entorno, "MOTIVO_CREAR")) == 1


@pytest.mark.parametrize("tipo", ["MOTIVO_CREAR", "MOTIVO_MODIFICAR"])
def test_por_el_lote_sin_el_permiso_responde_permiso_requerido_y_no_escribe(
    sesion: Session, tipo: str
) -> None:
    entorno = Entorno(sesion)
    existente = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
    contenido: dict[str, object] = (
        {"ambito": "AJUSTE_STOCK", "nombre": "Robo"}
        if tipo == "MOTIVO_CREAR"
        else {"motivo_id": str(existente), "nombre": "Cambiado", "activo": True}
    )
    item, usuario_id, dispositivo_id = _item_de_lote(
        entorno, tipo, "ONLINE", contenido, con_permiso=False
    )

    resultado = _procesar(sesion, entorno, item, usuario_id, dispositivo_id)

    assert resultado.estado == "RECHAZADO"
    assert resultado.error_codigo == "PERMISO_REQUERIDO"
    assert [f["nombre"] for f in _filas(entorno)] == ["Rotura"]


def test_no_hay_ruta_que_borre_un_motivo(cliente_http: TestClient, sesion: Session) -> None:
    # TR-06, CAT-05: ni `DELETE` ni `PATCH` sobre un motivo.
    entorno = Entorno(sesion)
    motivo = _crear_motivo(entorno, "AJUSTE_STOCK", "Rotura")
    headers = entorno.entrar(cliente_http)

    assert cliente_http.delete(_url(motivo), headers=con_op(headers)).status_code == 405
    assert cliente_http.patch(_url(motivo), json={}, headers=con_op(headers)).status_code == 405
    assert len(_filas(entorno)) == 1
