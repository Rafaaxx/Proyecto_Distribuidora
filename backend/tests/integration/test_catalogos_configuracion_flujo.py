"""Tarea 11.1 (change 20c): flujos de punta a punta de los catálogos de configuración, por HTTP
contra PostgreSQL real (specs `organizacion/catalogos-configurables`, `administracion-de-motivos`,
`administracion-de-alicuotas`, `parametros-de-organizacion`, `precios/administracion-de-listas`;
`design.md` D2 a D11).

Cada prueba encadena lo que el administrador hace en la pantalla con lo que las demás áreas
hacen después: un motivo creado se usa en un ajuste y en una anulación, dado de baja ya no se
acepta en una operación nueva y la anterior lo sigue mostrando; una alícuota nueva se asigna a un
producto, la vieja se da de baja cuando nadie activo la usa y una compra y una venta ya confirmadas
conservan el porcentaje con que se hicieron; el redondeo por defecto lo lee quien gestiona listas
y una lista nueva puede llevar otro.

Reglas citadas: TR-06, TR-09, STK-08, CAT-01, CAT-05, IMP-04, PRC-01, VTA-03, INV-01, INV-02,
INV-03, INV-05, INV-06, INV-21 y ADR-061.
"""

# ruff: noqa: F811  (las fixtures importadas se piden por nombre de parámetro)

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import medios_pago_utiles as utiles
from compras_utiles import Entorno as EntornoDeCompras
from cuentas_corrientes_utiles import crear_usuario_y_dispositivo
from fastapi.testclient import TestClient
from medios_pago_utiles import PASSWORD, Entorno, con_op
from sqlalchemy import text
from sqlalchemy.orm import Session
from stock_utiles import crear_producto_sql, crear_ubicacion_sql
from ventas_confirmar_utiles import EntornoVenta

from app.core.clock import FixedClock
from app.core.seguridad import hashear_password
from app.modules.configuracion import service as configuracion_service
from app.modules.stock import service as stock_service
from app.modules.stock.domain.movimientos import LineaDeStockInicial

_limpiar_datos_confirmados = utiles._limpiar_datos_confirmados
cliente_http = utiles.cliente_http
sesion = utiles.sesion

URL_MOTIVOS = "/api/v1/configuracion/motivos"
URL_ALICUOTAS = "/api/v1/configuracion/alicuotas"
URL_REDONDEO = "/api/v1/configuracion/redondeo-por-defecto"
URL_AJUSTES = "/api/v1/stock/ajustes"
URL_LISTAS = "/api/v1/precios/listas"
URL_PRODUCTOS = "/api/v1/catalogo/productos"

MOMENTO = utiles.MOMENTO


def _crear_motivo(cliente: TestClient, headers: dict[str, str], ambito: str, nombre: str) -> UUID:
    respuesta = cliente.post(
        URL_MOTIVOS, json={"ambito": ambito, "nombre": nombre}, headers=con_op(headers)
    )
    assert respuesta.status_code == 201, respuesta.text
    return UUID(respuesta.json()["id"])


def _cambiar_motivo(
    cliente: TestClient, headers: dict[str, str], motivo_id: UUID, nombre: str, activo: bool
) -> None:
    respuesta = cliente.put(
        f"{URL_MOTIVOS}/{motivo_id}",
        json={"nombre": nombre, "activo": activo},
        headers=con_op(headers),
    )
    assert respuesta.status_code == 200, respuesta.text


def _crear_alicuota(cliente: TestClient, headers: dict[str, str], nombre: str, valor: str) -> UUID:
    respuesta = cliente.post(
        URL_ALICUOTAS, json={"nombre": nombre, "valor": valor}, headers=con_op(headers)
    )
    assert respuesta.status_code == 201, respuesta.text
    return UUID(respuesta.json()["id"])


def _sembrar_alicuota_general(entorno: Entorno) -> UUID:
    alicuota_id = uuid4()
    entorno.sesion.execute(
        text(
            "INSERT INTO alicuota_iva (id, organizacion_id, nombre, valor, activo, creado_en, "
            "actualizado_en) VALUES (:id, :org, '21%', 0.210000, true, :m, :m)"
        ),
        {"id": alicuota_id, "org": entorno.org, "m": MOMENTO},
    )
    entorno.sesion.commit()
    return alicuota_id


# ======================= motivos: ajuste y anulación (TR-06, STK-08) ====================


def test_un_motivo_creado_se_usa_en_un_ajuste_y_en_su_anulacion_y_la_baja_corta_lo_nuevo(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.agregar_usuario("ajustador1", frozenset({"AJUSTAR_STOCK"}))
    deposito = crear_ubicacion_sql(sesion, entorno.org, nombre="Depósito")
    producto = crear_producto_sql(sesion, entorno.org)
    _, dispositivo = crear_usuario_y_dispositivo(sesion, entorno.org, permisos=frozenset())
    stock_service.registrar_stock_inicial(
        entorno.org,
        sesion,
        FixedClock(MOMENTO),
        ubicacion_id=deposito,
        lineas=[LineaDeStockInicial(producto, 100, "1050")],
        usuario_id=entorno.usuarios["ajustador1"],
        dispositivo_id=dispositivo,
        operation_id=uuid4(),
        occurred_at=MOMENTO,
    )
    sesion.commit()
    admin = entorno.entrar(cliente_http)
    ajustador = entorno.entrar(cliente_http, "ajustador1")
    robo = _crear_motivo(cliente_http, admin, "AJUSTE_STOCK", "Robo")
    _crear_motivo(cliente_http, admin, "AJUSTE_STOCK", "Rotura")
    error_de_carga = _crear_motivo(cliente_http, admin, "ANULACION_AJUSTE", "Error de carga")
    _crear_motivo(cliente_http, admin, "ANULACION_AJUSTE", "Ajuste duplicado")

    # El motivo nuevo se usa en un ajuste (STK-08) y el ajuste se anula con uno de su ámbito.
    primero = cliente_http.post(
        URL_AJUSTES,
        json={
            "ubicacion_id": str(deposito),
            "motivo_id": str(robo),
            "lineas": [{"producto_id": str(producto), "cantidad_base": -6}],
        },
        headers=con_op(ajustador),
    )
    assert primero.status_code == 201, primero.text
    ajuste = primero.json()["id"]
    anulado = cliente_http.post(
        f"{URL_AJUSTES}/{ajuste}/anulacion",
        json={"motivo_id": str(error_de_carga)},
        headers=con_op(ajustador),
    )
    assert anulado.status_code == 200, anulado.text

    # Renombrar: la operación anterior muestra el nombre nuevo (se guarda el id).
    _cambiar_motivo(cliente_http, admin, robo, "Robo en reparto", True)
    detalle = cliente_http.get(f"{URL_AJUSTES}/{ajuste}", headers=ajustador)
    assert detalle.json()["motivo_nombre"] == "Robo en reparto"

    # Baja: ya no se ofrece ni se acepta en una operación nueva; la anterior lo sigue mostrando.
    _cambiar_motivo(cliente_http, admin, robo, "Robo en reparto", False)
    ofrecidos = cliente_http.get(f"{URL_MOTIVOS}?ambito=AJUSTE_STOCK", headers=ajustador)
    segundo = cliente_http.post(
        URL_AJUSTES,
        json={
            "ubicacion_id": str(deposito),
            "motivo_id": str(robo),
            "lineas": [{"producto_id": str(producto), "cantidad_base": -1}],
        },
        headers=con_op(ajustador),
    )
    assert [m["nombre"] for m in ofrecidos.json()["items"]] == ["Rotura"]
    assert segundo.status_code in (409, 422), segundo.text
    assert segundo.json()["codigo"] == "MOTIVO_INVALIDO"
    detalle_despues = cliente_http.get(f"{URL_AJUSTES}/{ajuste}", headers=ajustador)
    assert detalle_despues.json()["motivo_nombre"] == "Robo en reparto"


def test_stk08_un_ajuste_con_un_motivo_dado_de_baja_se_rechaza_y_no_toca_el_stock(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.agregar_usuario("ajustador1", frozenset({"AJUSTAR_STOCK"}))
    deposito = crear_ubicacion_sql(sesion, entorno.org, nombre="Depósito")
    producto = crear_producto_sql(sesion, entorno.org)
    admin = entorno.entrar(cliente_http)
    ajustador = entorno.entrar(cliente_http, "ajustador1")
    merma = _crear_motivo(cliente_http, admin, "AJUSTE_STOCK", "Merma")
    _crear_motivo(cliente_http, admin, "AJUSTE_STOCK", "Rotura")
    _cambiar_motivo(cliente_http, admin, merma, "Merma", False)

    respuesta = cliente_http.post(
        URL_AJUSTES,
        json={
            "ubicacion_id": str(deposito),
            "motivo_id": str(merma),
            "lineas": [{"producto_id": str(producto), "cantidad_base": 5}],
        },
        headers=con_op(ajustador),
    )

    assert respuesta.json()["codigo"] == "MOTIVO_INVALIDO"
    sesion.rollback()
    movimientos = sesion.scalar(
        text("SELECT count(*) FROM stock_movimiento WHERE organizacion_id = :o"),
        {"o": entorno.org},
    )
    assert movimientos == 0


# ======================= alícuotas: producto, baja, importación (CAT-01, IMP-04) ========


def test_cat01_imp04_una_alicuota_nueva_reemplaza_a_la_vieja_en_productos_e_importacion(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.agregar_usuario("gestor1", frozenset({"GESTIONAR_CATALOGO"}))
    vieja = _sembrar_alicuota_general(entorno)
    producto_viejo = crear_producto_sql(sesion, entorno.org)
    sesion.commit()
    admin = entorno.entrar(cliente_http)
    gestor = entorno.entrar(cliente_http, "gestor1")
    nueva = _crear_alicuota(cliente_http, admin, "27%", "0.270000")
    sesion.execute(
        text("UPDATE producto SET alicuota_id = :a WHERE id = :p"),
        {"a": vieja, "p": producto_viejo},
    )
    sesion.commit()

    # Mientras un producto activo la use, la vieja no se da de baja (informa la cantidad).
    en_uso = cliente_http.put(
        f"{URL_ALICUOTAS}/{vieja}",
        json={"nombre": "21%", "valor": "0.210000", "activo": False},
        headers=con_op(admin),
    )
    assert en_uso.status_code == 409
    assert (en_uso.json()["codigo"], en_uso.json()["productos"]) == ("ALICUOTA_EN_USO", 1)

    # Se pasa el producto a la nueva por el catálogo (CAT-01) y entonces la vieja se da de baja.
    producto = cliente_http.get(f"{URL_PRODUCTOS}/{producto_viejo}", headers=gestor)
    assert producto.status_code == 200, producto.text
    pasado = cliente_http.put(
        f"{URL_PRODUCTOS}/{producto_viejo}",
        json={**_cuerpo_de_modificacion(producto.json()), "alicuota_id": str(nueva)},
        headers=con_op(gestor),
    )
    assert pasado.status_code == 200, pasado.text
    baja = cliente_http.put(
        f"{URL_ALICUOTAS}/{vieja}",
        json={"nombre": "21%", "valor": "0.210000", "activo": False},
        headers=con_op(admin),
    )
    assert baja.status_code == 200, baja.text

    # IMP-04: la importación por porcentaje resuelve la nueva sin ambigüedad, y no puede haber dos.
    sesion.rollback()
    [encontrada] = configuracion_service.buscar_alicuotas_por_valor(
        entorno.org, Decimal("0.27"), sesion
    )
    assert encontrada.id == nueva
    repetida = cliente_http.post(
        URL_ALICUOTAS, json={"nombre": "Otra 27", "valor": "0.270000"}, headers=con_op(admin)
    )
    assert repetida.json()["codigo"] == "VALOR_DUPLICADO"
    # Un producto nuevo ya no puede nacer con la vieja de baja.
    con_la_vieja = cliente_http.put(
        f"{URL_PRODUCTOS}/{producto_viejo}",
        json={**_cuerpo_de_modificacion(producto.json()), "alicuota_id": str(vieja)},
        headers=con_op(gestor),
    )
    assert con_la_vieja.json()["codigo"] == "ALICUOTA_INACTIVA"


def _cuerpo_de_modificacion(producto: dict[str, object]) -> dict[str, object]:
    """El cuerpo de `PUT /catalogo/productos/{id}` a partir de lo que devuelve el detalle."""
    return {
        clave: producto[clave]
        for clave in (
            "codigo",
            "nombre",
            "categoria_id",
            "marca_id",
            "proveedor_id",
            "unidad_base",
            "alicuota_id",
            "activo",
        )
        if clave in producto
    }


# ======================= historia congelada con una compra y una venta reales (TR-06, VTA-03)


def _entrar_como_administrador(
    cliente: TestClient, sesion: Session, organizacion_id: UUID
) -> dict[str, str]:
    """Un usuario con `ADMIN_CONFIGURACION` y contraseña conocida en la organización dada."""
    usuario_id, _ = crear_usuario_y_dispositivo(
        sesion, organizacion_id, permisos=frozenset({"ADMIN_CONFIGURACION"})
    )
    sesion.execute(
        text("UPDATE usuario SET password_hash = :h WHERE organizacion_id = :o AND id = :u"),
        {"h": hashear_password(PASSWORD), "o": organizacion_id, "u": usuario_id},
    )
    sesion.commit()
    usuario, slug = sesion.execute(
        text(
            "SELECT u.usuario, o.slug FROM usuario u "
            "JOIN organizacion o ON o.id = u.organizacion_id "
            "WHERE u.organizacion_id = :o AND u.id = :u"
        ),
        {"o": organizacion_id, "u": usuario_id},
    ).one()
    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={
            "organizacion_slug": slug,
            "usuario": usuario,
            "contrasena": PASSWORD,
            "dispositivo_id": str(uuid4()),
            "nombre_dispositivo": "PC",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _renombrar_y_dar_de_baja_la_general(
    cliente: TestClient, sesion: Session, organizacion_id: UUID
) -> None:
    """Crea la 27 %, retira de uso los productos y renombra y da de baja la 21 %."""
    admin = _entrar_como_administrador(cliente, sesion, organizacion_id)
    _crear_alicuota(cliente, admin, "27%", "0.270000")
    sesion.execute(
        text("UPDATE producto SET activo = false WHERE organizacion_id = :o"),
        {"o": organizacion_id},
    )
    sesion.commit()
    general = sesion.scalar(
        text("SELECT id FROM alicuota_iva WHERE organizacion_id = :o AND valor = 0.210000"),
        {"o": organizacion_id},
    )
    renombrada = cliente.put(
        f"{URL_ALICUOTAS}/{general}",
        json={"nombre": "IVA general", "valor": "0.210000", "activo": True},
        headers=con_op(admin),
    )
    baja = cliente.put(
        f"{URL_ALICUOTAS}/{general}",
        json={"nombre": "IVA general", "valor": "0.210000", "activo": False},
        headers=con_op(admin),
    )
    assert renombrada.status_code == baja.status_code == 200, baja.text


def test_tr06_una_compra_confirmada_conserva_su_alicuota_al_renombrar_y_dar_de_baja(
    cliente_http: TestClient, sesion: Session
) -> None:
    compras = EntornoDeCompras(sesion)
    compras.enviar()
    sesion.commit()
    antes = [str(linea.alicuota_aplicada) for linea in compras.lineas()]
    assert antes and set(antes) == {"0.210000"}

    _renombrar_y_dar_de_baja_la_general(cliente_http, sesion, compras.org)

    sesion.rollback()
    despues = [str(linea.alicuota_aplicada) for linea in compras.lineas()]
    assert despues == antes


def test_vta03_una_venta_confirmada_conserva_su_alicuota_al_renombrar_y_dar_de_baja(
    cliente_http: TestClient, sesion: Session
) -> None:
    ventas = EntornoVenta(sesion)
    ventas.vender()
    sesion.commit()
    [venta] = ventas.ventas()
    antes = [str(linea.alicuota) for linea in ventas.lineas_de_venta(venta.id)]
    assert antes and set(antes) == {"0.210000"}

    _renombrar_y_dar_de_baja_la_general(cliente_http, sesion, ventas.org)

    sesion.rollback()
    despues = [str(linea.alicuota) for linea in ventas.lineas_de_venta(venta.id)]
    assert despues == antes


# ======================= redondeo por defecto y listas (PRC-01) =========================


def test_prc01_el_redondeo_por_defecto_lo_lee_quien_gestiona_listas_y_la_lista_puede_llevar_otro(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.agregar_usuario("listas1", frozenset({"GESTIONAR_LISTAS"}))
    admin = entorno.entrar(cliente_http)
    gestor = entorno.entrar(cliente_http, "listas1")

    sin_definir = cliente_http.get(URL_REDONDEO, headers=gestor)
    definido = cliente_http.post(
        URL_REDONDEO, json={"multiplo": "500.00", "direccion": "ABAJO"}, headers=con_op(admin)
    )
    leido = cliente_http.get(URL_REDONDEO, headers=gestor)
    lista = cliente_http.post(
        URL_LISTAS,
        json={"nombre": "Mayorista", "redondeo_multiplo": "50.00", "redondeo_direccion": "CERCANO"},
        headers=con_op(gestor),
    )
    despues = cliente_http.get(URL_REDONDEO, headers=gestor)

    assert (sin_definir.status_code, sin_definir.json()) == (
        200,
        {"multiplo": None, "direccion": None},
    )
    assert definido.status_code == 200, definido.text
    assert leido.json() == {"multiplo": "500.00", "direccion": "ABAJO"}
    assert lista.status_code == 201, lista.text
    assert (lista.json()["redondeo_multiplo"], lista.json()["redondeo_direccion"]) == (
        "50.00",
        "CERCANO",
    )
    # La lista creada con otro redondeo no cambia el parámetro de la organización.
    assert despues.json() == {"multiplo": "500.00", "direccion": "ABAJO"}


def test_prc01_quitar_el_redondeo_por_defecto_lo_deja_sin_definir_y_un_vendedor_no_lo_lee(
    cliente_http: TestClient, sesion: Session
) -> None:
    entorno = Entorno(sesion)
    entorno.agregar_usuario("vendedor1", frozenset({"VENDER"}))
    admin = entorno.entrar(cliente_http)
    vendedor = entorno.entrar(cliente_http, "vendedor1")
    cliente_http.post(
        URL_REDONDEO, json={"multiplo": "500.00", "direccion": "ABAJO"}, headers=con_op(admin)
    )

    quitado = cliente_http.post(
        URL_REDONDEO, json={"multiplo": None, "direccion": None}, headers=con_op(admin)
    )

    assert quitado.status_code == 200, quitado.text
    assert cliente_http.get(URL_REDONDEO, headers=admin).json() == {
        "multiplo": None,
        "direccion": None,
    }
    assert cliente_http.get(URL_REDONDEO, headers=vendedor).status_code == 403
