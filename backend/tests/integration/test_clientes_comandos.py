"""Change 07, grupo 3 contra el bus y PostgreSQL real (`tests/integration`).

Las pruebas unitarias de `test_clientes_commands.py` sustituyen el servicio y
la sesión por dobles: verifican el catálogo, los esquemas, el permiso de cada
comando y la delegación. Lo que NO se puede ver sin la base real es otra cosa,
y es justo lo que importa acá:

- que el handler no cierre la transacción y la reversión del bus se lleve
  también la auditoría y el cliente creado (INV-01);
- que un `IntegrityError` por índice duplicado salga como error de dominio y no
  como `IntegrityError` crudo (D1, `ux_cliente__codigo`, `ux_cliente__documento`);
- que la idempotencia por `operation_id` devuelva el MISMO resultado y no
  duplique la fila ni la auditoría (SYN-07);
- que la búsqueda por texto con dígitos encuentre de verdad el documento
  normalizado, que es donde una condición mal armada se ve como un listado
  vacío;
- que el par del consumidor final (cliente + configuración) quede escrito
  entero, o no quede nada.

Mismo criterio que `test_proveedores_commands_bus.py`: se procesa el comando
por `sync_service.procesar_comando`, que es el que maneja la transacción, en
lugar de llamar al handler directo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands import registro
from app.commands.huella import calcular_huella
from app.commands.sobre import SobreComando
from app.core.clock import FixedClock
from app.core.errors import DomainError
from app.core.ids import nuevo_id
from app.modules.clientes import commands as clientes_commands
from app.modules.clientes import repository as clientes_repository
from app.modules.clientes.domain.errores import (
    ClienteConOperacionesError,
    CodigoDuplicadoError,
    ConfiguracionDeOrganizacionAusenteError,
    ConsumidorFinalNoInactivableError,
    ConsumidorFinalYaHabilitadoError,
    DocumentoDuplicadoError,
    RecursoNoEncontradoError,
    TransicionEstadoInvalidaError,
)
from app.modules.clientes.models import Cliente
from app.modules.cuentas_corrientes import service as cuentas_corrientes_service
from app.modules.identidad import repository as identidad_repository
from app.modules.identidad.models import Auditoria, ConfiguracionOrganizacion, Organizacion
from app.modules.proveedores import (
    models as _proveedores_models,  # noqa: F401 (FK de cuentas_corrientes)
)
from app.modules.sync import service as sync_service
from app.modules.sync.models import Comando

pytestmark = pytest.mark.usefixtures("_engine_de_sesion")

MOMENTO = datetime(2026, 1, 1, tzinfo=UTC)
RELOJ = FixedClock(MOMENTO)

TODOS = frozenset({"GESTIONAR_CLIENTES", "GESTIONAR_CREDITO", "ADMIN_CONFIGURACION"})


# --- utilidades ------------------------------------------------------------


def _crear_organizacion(sesion: Session, *, con_configuracion: bool = True) -> Organizacion:
    organizacion = Organizacion(
        id=nuevo_id(),
        nombre="Organización de prueba clientes",
        slug=f"org-clientes-{uuid4().hex[:8]}",
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
    if con_configuracion:
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


def _crear_usuario_y_dispositivo(
    sesion: Session, organizacion_id: UUID, *, permisos: frozenset[str] = TODOS
) -> tuple[UUID, UUID]:
    rol = identidad_repository.crear_rol(
        organizacion_id,
        sesion,
        rol_id=nuevo_id(),
        nombre="Gestor de clientes",
        tope_descuento=Decimal("0"),
        activo=True,
        momento=MOMENTO,
    )
    for codigo in sorted(permisos):
        identidad_repository.asignar_permiso_a_rol(
            organizacion_id, sesion, rol_id=rol.id, permiso_codigo=codigo
        )
    usuario = identidad_repository.crear_usuario(
        organizacion_id,
        sesion,
        usuario_id=nuevo_id(),
        usuario=f"gestor-{uuid4().hex[:8]}",
        nombre="Persona de prueba",
        email=None,
        password_hash="hash",
        rol_id=rol.id,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    dispositivo = identidad_repository.crear_dispositivo(
        organizacion_id,
        sesion,
        dispositivo_id=nuevo_id(),
        nombre="Dispositivo de prueba",
        prefijo=f"C{uuid4().hex[:2]}",
        ultimo_correlativo=0,
        estado="ACTIVO",
        momento=MOMENTO,
    )
    return usuario.id, dispositivo.id


def _sobre(
    *,
    tipo: str,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    contenido: dict[str, object],
    operation_id: UUID | None = None,
) -> SobreComando:
    return SobreComando(
        operation_id=operation_id or uuid4(),
        tipo=tipo,
        version=1,
        modo="ONLINE",
        organizacion_id=organizacion_id,
        usuario_id=usuario_id,
        dispositivo_id=dispositivo_id,
        occurred_at=MOMENTO,
        secuencia=1,
        app_version="1.0.0",
        contenido=contenido,  # type: ignore[arg-type]
    )


def _procesar(sesion: Session, sobre: SobreComando, *, handler: Any, contenido_cls: Any) -> Comando:
    """Procesa el comando por el bus, que es quien maneja la transacción.

    El contenido se valida con `registro.validar_contenido`, que es la llamada
    que hace `sync/service.py`, y no con un `model_validate` directo: así una
    violación de esquema sale como `CONTENIDO_DE_COMANDO_INVALIDO` (SYN-06) y no
    como un `ValidationError` de Pydantic que el bus real nunca vería. `handler` y
    `contenido_cls` siguen declarándose para que cada prueba cite el handler que
    exercise."""
    huella = calcular_huella(sobre.contenido)
    registrado = registro.resolver_handler(sobre.tipo, sobre.version)
    contenido_validado = registro.validar_contenido(registrado, sobre.contenido)
    assert isinstance(contenido_validado, contenido_cls), (
        f"El esquema registrado de {sobre.tipo} no es el que la prueba declara."
    )

    def _ejecutar(sesion_protegida: object) -> sync_service.ResultadoHandler:
        return handler(sobre, contenido_validado, sesion=sesion_protegida, reloj=RELOJ)

    return sync_service.procesar_comando(
        sesion, RELOJ, sobre=sobre, huella=huella, ejecutar_handler=_ejecutar
    )


def _cuerpo_crear(**cambios: object) -> dict[str, object]:
    """Contenido de `CLIENTE_CREAR` con los valores por defecto de las pruebas."""
    cuerpo: dict[str, object] = {
        "nombre": "Kiosco La Esquina",
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "razon_social": None,
        "documento_tipo": None,
        "documento_numero": None,
        "telefono": None,
        "email": None,
        "codigo": None,
        "estado_facturacion_default": None,
    }
    cuerpo.update(cambios)
    return cuerpo


def _crear(
    sesion: Session,
    *,
    organizacion_id: UUID,
    usuario_id: UUID,
    dispositivo_id: UUID,
    **contenido: object,
) -> Comando:
    return _procesar(
        sesion,
        _sobre(
            tipo="CLIENTE_CREAR",
            organizacion_id=organizacion_id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            contenido=_cuerpo_crear(**contenido),
        ),
        handler=clientes_commands.manejar_cliente_crear,
        contenido_cls=clientes_commands.ClienteCrearContenidoV1,
    )


def _ficha(cliente_id: UUID, *, estado: str, **cambios: object) -> dict[str, object]:
    """Contenido entero de `CLIENTE_MODIFICAR`, que manda la ficha completa."""
    cuerpo: dict[str, object] = {
        "cliente_id": str(cliente_id),
        "nombre": "Kiosco La Esquina",
        "direccion": "Av. San Martín 1420",
        "contacto": "Rocío",
        "estado": estado,
        "razon_social": None,
        "documento_tipo": None,
        "documento_numero": None,
        "telefono": None,
        "email": None,
        "codigo": None,
        "estado_facturacion_default": None,
    }
    cuerpo.update(cambios)
    return cuerpo


def _clientes_de(sesion: Session, organizacion_id: UUID) -> list[Cliente]:
    return list(
        sesion.scalars(
            select(Cliente)
            .where(Cliente.organizacion_id == organizacion_id)
            .order_by(Cliente.nombre)
        ).all()
    )


def _auditorias_de(sesion: Session, organizacion_id: UUID, accion: str) -> list[Auditoria]:
    """Las auditorías de la ESCRITURA, no las del comando.

    Filtra por `entidad='cliente'`: el bus escribe además una fila propia por
    cada comando ejecutado (`sync/service.py::procesar_comando`, `accion` =
    tipo del comando, `entidad` = `'comando'`), y sin este filtro la de la
    escritura de crédito y la del comando se contarían como dos.
    """
    return list(
        sesion.scalars(
            select(Auditoria)
            .where(
                Auditoria.organizacion_id == organizacion_id,
                Auditoria.accion == accion,
                Auditoria.entidad == "cliente",
            )
            .order_by(Auditoria.registered_at)
        ).all()
    )


# --- CLIENTE_CREAR ---------------------------------------------------------


class TestClienteCrearContraElBus:
    def test_crea_el_cliente_audita_y_el_reenvio_no_duplica(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        operation_id = uuid4()
        sobre = _sobre(
            tipo="CLIENTE_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            contenido=_cuerpo_crear(
                nombre="Distribuidora Sur",
                direccion="Ruta 5 km 12",
                contacto="Nico",
                codigo="PROV-001",
            ),
            operation_id=operation_id,
        )

        primero = _procesar(
            db_session,
            sobre,
            handler=clientes_commands.manejar_cliente_crear,
            contenido_cls=clientes_commands.ClienteCrearContenidoV1,
        )
        segundo = _procesar(
            db_session,
            sobre,
            handler=clientes_commands.manejar_cliente_crear,
            contenido_cls=clientes_commands.ClienteCrearContenidoV1,
        )

        assert primero.estado == "ACEPTADO"
        assert primero.resultado == segundo.resultado, (
            "El reenvío del mismo `operation_id` tiene que devolver el mismo "
            "resultado (SYN-07), no crear un segundo cliente."
        )
        clientes = _clientes_de(db_session, organizacion.id)
        assert [c.nombre for c in clientes] == ["Distribuidora Sur"]
        assert clientes[0].estado == "ACTIVO", "El cliente nace `ACTIVO` (D7)."
        assert clientes[0].limite_credito is None, (
            "El alta no escribe crédito: sale heredando (D8)."
        )
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(Comando)
                .where(Comando.operation_id == operation_id)
            )
            == 1
        )

    def test_el_cliente_se_normaliza_antes_de_guardar(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            nombre="  kiosco   la  esquina ",
            documento_tipo="DNI",
            documento_numero="30-111 222",
        )

        cliente = _clientes_de(db_session, organizacion.id)[0]
        assert cliente.nombre == "kiosco   la  esquina", (
            "El nombre se recorta en los bordes y nada más: los espacios de "
            "adentro son parte del nombre (mismo criterio que el nombre del "
            "proveedor, D7 del change 06, y que `test_clientes_domain.py`)."
        )
        assert cliente.documento_numero == "30111222", (
            "El documento se guarda normalizado a solo dígitos (D1), que es lo "
            "que hace que la comparación unívoca sea posible."
        )

    def test_un_codigo_repetido_sale_como_error_de_dominio(self, db_session: Session) -> None:
        """D1: el índice parcial `ux_cliente__codigo` es lo que separa dos altas
        concurrentes. Su `IntegrityError` tiene que traducirse a un error con
        código estable, no subir crudo a la API."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            nombre="Kiosco Uno",
            codigo="COMPARTIDO",
        )
        with pytest.raises(CodigoDuplicadoError) as excepcion:
            _crear(
                db_session,
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                nombre="Kiosco Dos",
                codigo="COMPARTIDO",
            )

        assert excepcion.value.codigo == "CODIGO_DUPLICADO"
        assert [c.nombre for c in _clientes_de(db_session, organizacion.id)] == ["Kiosco Uno"], (
            "El rechazo no puede dejar el segundo cliente a medias (INV-01)."
        )

    def test_un_documento_repetido_sale_como_error_de_dominio(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        # Un cliente con el documento YA NORMALIZADO, y después el mismo
        # documento escrito con separadores: el índice es sobre los dígitos, así
        # que el segundo tiene que chocar aunque las cadenas sean distintas.
        _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            nombre="Kiosco Uno",
            documento_tipo="DNI",
            documento_numero="30111222",
        )
        db_session.commit()

        with pytest.raises(DocumentoDuplicadoError) as excepcion:
            _crear(
                db_session,
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                nombre="Kiosco Tres",
                documento_tipo="DNI",
                documento_numero="30-111 222",
            )

        assert excepcion.value.codigo == "DOCUMENTO_DUPLICADO", (
            "El índice es sobre el documento NORMALIZADO: `30-111 222` y "
            "`30111222` son el mismo cliente (D1)."
        )

    def test_el_credito_del_contenido_se_rechaza_sin_crear_nada(self, db_session: Session) -> None:
        """D3: mandar el crédito en el comando de ficha es contenido malformado.
        Lo que no puede ser es que se acepte en silencio."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        sobre = _sobre(
            tipo="CLIENTE_CREAR",
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            contenido={
                "nombre": "Kiosco",
                "direccion": "Av. 1",
                "contacto": "Nico",
                "limite_credito": "1.00",
            },
        )
        with pytest.raises(DomainError) as excepcion:
            _procesar(
                db_session,
                sobre,
                handler=clientes_commands.manejar_cliente_crear,
                contenido_cls=clientes_commands.ClienteCrearContenidoV1,
            )

        assert excepcion.value.codigo == "CONTENIDO_DE_COMANDO_INVALIDO"
        assert _clientes_de(db_session, organizacion.id) == []


# --- CLIENTE_MODIFICAR -----------------------------------------------------


class TestClienteModificarContraElBus:
    def test_inactiva_un_cliente_sin_operaciones(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]

        _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_MODIFICAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido=_ficha(cliente_id, estado="INACTIVO", direccion="Av. San Martín 1430"),
            ),
            handler=clientes_commands.manejar_cliente_modificar,
            contenido_cls=clientes_commands.ClienteModificarContenidoV1,
        )

        cliente = _clientes_de(db_session, organizacion.id)[0]
        assert cliente.estado == "INACTIVO"
        assert cliente.direccion == "Av. San Martín 1430"

    def test_un_cliente_inactivo_sin_operaciones_vuelve_a_activo(self, db_session: Session) -> None:
        """D7, opción C aprobada (CLI-06, ADR-030): `INACTIVO -> ACTIVO` está
        permitido mientras el cliente no tenga operaciones.

        Sin movimientos en su cuenta corriente (change 08, D8) el cliente no
        tiene operaciones. El caso con movimientos es
        `TestReactivacionConMovimientos`."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]

        for estado in ("INACTIVO", "ACTIVO"):
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_MODIFICAR",
                    organizacion_id=organizacion.id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    contenido=_ficha(cliente_id, estado=estado),
                ),
                handler=clientes_commands.manejar_cliente_modificar,
                contenido_cls=clientes_commands.ClienteModificarContenidoV1,
            )

        assert _clientes_de(db_session, organizacion.id)[0].estado == "ACTIVO"

    def test_desde_inactivo_no_se_puede_pasar_a_suspendido(self, db_session: Session) -> None:
        """La única salida de `INACTIVO` que la máquina admite es hacia `ACTIVO`
        y solo sin operaciones. `INACTIVO -> SUSPENDIDO` no está en `01` §18."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]

        _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_MODIFICAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido=_ficha(cliente_id, estado="INACTIVO"),
            ),
            handler=clientes_commands.manejar_cliente_modificar,
            contenido_cls=clientes_commands.ClienteModificarContenidoV1,
        )

        with pytest.raises(TransicionEstadoInvalidaError) as excepcion:
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_MODIFICAR",
                    organizacion_id=organizacion.id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    contenido=_ficha(cliente_id, estado="SUSPENDIDO"),
                ),
                handler=clientes_commands.manejar_cliente_modificar,
                contenido_cls=clientes_commands.ClienteModificarContenidoV1,
            )

        assert excepcion.value.codigo == "TRANSICION_ESTADO_INVALIDA"
        assert _clientes_de(db_session, organizacion.id)[0].estado == "INACTIVO", (
            "El rechazo no puede haber dejado el cliente en el estado pedido."
        )

    def test_el_consumidor_final_no_se_inactiva(self, db_session: Session) -> None:
        """CLI-03, ADR-029: el consumidor final solo puede estar `ACTIVO` o
        `SUSPENDIDO`. Inactivarlo dejaría la venta "de paso" apagada por un
        cambio de estado; para dejar de vender se deshabilita la función con el
        comando de habilitación."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido={"nombre": "Consumidor final"},
            ),
            handler=clientes_commands.manejar_cliente_consumidor_final_configurar,
            contenido_cls=clientes_commands.ClienteConsumidorFinalConfigurarContenidoV1,
        )
        db_session.commit()
        cliente = _clientes_de(db_session, organizacion.id)[0]

        with pytest.raises(ConsumidorFinalNoInactivableError) as excepcion:
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_MODIFICAR",
                    organizacion_id=organizacion.id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    contenido=_ficha(cliente.id, estado="INACTIVO"),
                ),
                handler=clientes_commands.manejar_cliente_modificar,
                contenido_cls=clientes_commands.ClienteModificarContenidoV1,
            )

        assert excepcion.value.codigo == "CONSUMIDOR_FINAL_NO_INACTIVABLE"
        assert _clientes_de(db_session, organizacion.id)[0].estado == "ACTIVO"

    def test_el_cliente_de_otra_organizacion_no_existe(self, db_session: Session) -> None:
        """INV-21, TR-08: un `cliente_id` ajeno responde como inexistente, y con
        el mismo código que un id que nunca existió. Un 403 o un 404 de
        "no es tuyo" confirmarían que el identificador existe."""
        org_a = _crear_organizacion(db_session)
        org_b = _crear_organizacion(db_session)
        usuario_a, dispositivo_a = _crear_usuario_y_dispositivo(db_session, org_a.id)
        usuario_b, dispositivo_b = _crear_usuario_y_dispositivo(db_session, org_b.id)
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=org_a.id,
            usuario_id=usuario_a,
            dispositivo_id=dispositivo_a,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]

        cuerpo: dict[str, object] = _ficha(
            cliente_id, estado="SUSPENDIDO", nombre="Secuestro", direccion="Otra", contacto="Otro"
        )
        with pytest.raises(RecursoNoEncontradoError) as ajeno:
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_MODIFICAR",
                    organizacion_id=org_b.id,
                    usuario_id=usuario_b,
                    dispositivo_id=dispositivo_b,
                    contenido=cuerpo,
                ),
                handler=clientes_commands.manejar_cliente_modificar,
                contenido_cls=clientes_commands.ClienteModificarContenidoV1,
            )
        with pytest.raises(RecursoNoEncontradoError) as inexistente:
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_MODIFICAR",
                    organizacion_id=org_b.id,
                    usuario_id=usuario_b,
                    dispositivo_id=dispositivo_b,
                    contenido={**cuerpo, "cliente_id": str(uuid4())},
                ),
                handler=clientes_commands.manejar_cliente_modificar,
                contenido_cls=clientes_commands.ClienteModificarContenidoV1,
            )

        assert ajeno.value.codigo == inexistente.value.codigo
        assert _clientes_de(db_session, org_a.id)[0].estado == "ACTIVO", (
            "El intento de org B no puede haber tocado el cliente de org A."
        )


# --- CLIENTE_CREDITO_MODIFICAR --------------------------------------------


class TestClienteCreditoModificarContraElBus:
    def test_escribe_el_credito_y_lo_audita_con_el_antes_y_el_despues(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]
        db_session.commit()

        _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_CREDITO_MODIFICAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido={
                    "cliente_id": str(cliente_id),
                    "limite_credito": "150000.00",
                    "politica_credito": "AUTORIZAR",
                    "tolerancia_offline_tipo": "IMPORTE",
                    "tolerancia_offline_valor": "5000.00",
                },
            ),
            handler=clientes_commands.manejar_cliente_credito_modificar,
            contenido_cls=clientes_commands.ClienteCreditoModificarContenidoV1,
        )

        cliente = _clientes_de(db_session, organizacion.id)[0]
        assert cliente.limite_credito == Decimal("150000.00")
        assert cliente.politica_credito == "AUTORIZAR"
        assert cliente.tolerancia_offline_tipo == "IMPORTE"
        assert cliente.tolerancia_offline_valor == Decimal("5000.00")
        assert cliente.nombre == "Kiosco La Esquina", "El comando de crédito no toca la ficha (D3)."

        auditorias = _auditorias_de(db_session, organizacion.id, "CLIENTE_CREDITO_MODIFICAR")
        assert len(auditorias) == 1
        assert auditorias[0].entidad == "cliente"
        assert auditorias[0].entidad_id == cliente_id
        assert auditorias[0].antes == {
            "limite_credito": None,
            "politica_credito": None,
            "tolerancia_offline_tipo": None,
            "tolerancia_offline_valor": None,
        }, "El alta no escribe crédito: el `antes` de la primera modificación es todo `None`."
        assert auditorias[0].despues == {
            "limite_credito": "150000.00",
            "politica_credito": "AUTORIZAR",
            "tolerancia_offline_tipo": "IMPORTE",
            "tolerancia_offline_valor": "5000.00",
        }, (
            "Los importes de `antes`/`despues` viajan como string porque las "
            "columnas son `jsonb` y JSON no tiene decimal (INV-03, `CLAUDE.md` §4)."
        )

    def test_ningun_campo_en_nulo_deja_el_credito_heredando(self, db_session: Session) -> None:
        """D8, CRE-03: `None` significa HEREDAR, no "cero" ni "sin cambio".
        La fila queda con los tres en `None` y la herencia se resuelve cuando se
        evalúa el crédito, en el change 18b."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]
        db_session.commit()

        _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_CREDITO_MODIFICAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido={
                    "cliente_id": str(cliente_id),
                    "limite_credito": "150000.00",
                    "politica_credito": "AUTORIZAR",
                    "tolerancia_offline_tipo": None,
                    "tolerancia_offline_valor": None,
                },
            ),
            handler=clientes_commands.manejar_cliente_credito_modificar,
            contenido_cls=clientes_commands.ClienteCreditoModificarContenidoV1,
        )
        _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_CREDITO_MODIFICAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido={
                    "cliente_id": str(cliente_id),
                    "limite_credito": None,
                    "politica_credito": None,
                    "tolerancia_offline_tipo": None,
                    "tolerancia_offline_valor": None,
                },
            ),
            handler=clientes_commands.manejar_cliente_credito_modificar,
            contenido_cls=clientes_commands.ClienteCreditoModificarContenidoV1,
        )

        cliente = _clientes_de(db_session, organizacion.id)[0]
        assert cliente.limite_credito is None
        assert cliente.politica_credito is None
        # La organización tiene `ADVERTIR` como política por defecto, y el
        # cliente NO la copió: heredarla es resolverla al evaluar.
        configuracion = db_session.get(ConfiguracionOrganizacion, organizacion.id)
        assert configuracion is not None
        assert configuracion.politica_credito_default == "ADVERTIR"
        assert cliente.politica_credito != configuracion.politica_credito_default

    def test_sin_el_permiso_de_credito_no_escribe_nada(self, db_session: Session) -> None:
        """D3: `GESTIONAR_CLIENTES` no alcanza para el crédito. Un rol de
        ventas/edición ve la ficha y no la línea de crédito."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        db_session.commit()
        creado = _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]
        db_session.commit()

        with pytest.raises(DomainError) as excepcion:
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_CREDITO_MODIFICAR",
                    organizacion_id=organizacion.id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    contenido={"cliente_id": str(cliente_id), "limite_credito": "999999.00"},
                ),
                handler=clientes_commands.manejar_cliente_credito_modificar,
                contenido_cls=clientes_commands.ClienteCreditoModificarContenidoV1,
            )

        assert excepcion.value.codigo == "PERMISO_REQUERIDO"
        assert excepcion.value.status_http == 403
        assert _clientes_de(db_session, organizacion.id)[0].limite_credito is None
        assert _auditorias_de(db_session, organizacion.id, "CLIENTE_CREDITO_MODIFICAR") == []


# --- CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR ----------------------------------


class TestConsumidorFinalContraElBus:
    def test_escribe_el_cliente_y_la_configuracion_juntos(self, db_session: Session) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        comando = _procesar(
            db_session,
            _sobre(
                tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
                organizacion_id=organizacion.id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido={"nombre": "Consumidor final de la organización"},
            ),
            handler=clientes_commands.manejar_cliente_consumidor_final_configurar,
            contenido_cls=clientes_commands.ClienteConsumidorFinalConfigurarContenidoV1,
        )

        cliente_id = UUID(comando.resultado["cliente_id"])  # type: ignore[index]
        configuracion = db_session.get(ConfiguracionOrganizacion, organizacion.id)
        assert configuracion is not None
        assert configuracion.permite_consumidor_final is True
        assert configuracion.cliente_consumidor_final_id == cliente_id, (
            "D4: los dos campos son un par. La referencia tiene que apuntar al "
            "cliente que este mismo comando creó."
        )

        cliente = _clientes_de(db_session, organizacion.id)[0]
        assert cliente.es_consumidor_final is True
        assert cliente.limite_credito == Decimal("0.00"), (
            "CLI-03: el consumidor final no tiene crédito propio."
        )
        assert cliente.estado == "ACTIVO"
        assert cliente.direccion, (
            "La dirección y el contacto los pone el servicio, no el contenido."
        )

    def test_el_segundo_intento_se_rechaza_sin_crear_otro_cliente(
        self, db_session: Session
    ) -> None:
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        for _ in range(2):
            cuerpo: dict[str, object] = {"nombre": "Consumidor final"}
            if _clientes_de(db_session, organizacion.id):
                with pytest.raises(ConsumidorFinalYaHabilitadoError) as excepcion:
                    _procesar(
                        db_session,
                        _sobre(
                            tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
                            organizacion_id=organizacion.id,
                            usuario_id=usuario_id,
                            dispositivo_id=dispositivo_id,
                            contenido=cuerpo,
                        ),
                        handler=clientes_commands.manejar_cliente_consumidor_final_configurar,
                        contenido_cls=clientes_commands.ClienteConsumidorFinalConfigurarContenidoV1,
                    )
                assert excepcion.value.codigo == "CONSUMIDOR_FINAL_YA_HABILITADO"
            else:
                _procesar(
                    db_session,
                    _sobre(
                        tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
                        organizacion_id=organizacion.id,
                        usuario_id=usuario_id,
                        dispositivo_id=dispositivo_id,
                        contenido=cuerpo,
                    ),
                    handler=clientes_commands.manejar_cliente_consumidor_final_configurar,
                    contenido_cls=clientes_commands.ClienteConsumidorFinalConfigurarContenidoV1,
                )
            db_session.commit()

        marcados = [c for c in _clientes_de(db_session, organizacion.id) if c.es_consumidor_final]
        assert len(marcados) == 1, "El segundo intento no puede crear un segundo consumidor final."

    def test_sin_permiso_de_configuracion_no_habilita_nada(self, db_session: Session) -> None:
        """D4: el permiso es `ADMIN_CONFIGURACION`, no `GESTIONAR_CLIENTES`,
        porque el comando escribe la configuración de la organización."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(
            db_session, organizacion.id, permisos=frozenset({"GESTIONAR_CLIENTES"})
        )
        db_session.commit()

        with pytest.raises(DomainError) as excepcion:
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
                    organizacion_id=organizacion.id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    contenido={"nombre": "Consumidor final"},
                ),
                handler=clientes_commands.manejar_cliente_consumidor_final_configurar,
                contenido_cls=clientes_commands.ClienteConsumidorFinalConfigurarContenidoV1,
            )

        assert excepcion.value.codigo == "PERMISO_REQUERIDO"
        configuracion = db_session.get(ConfiguracionOrganizacion, organizacion.id)
        assert configuracion is not None
        assert configuracion.permite_consumidor_final is None
        assert configuracion.cliente_consumidor_final_id is None
        assert _clientes_de(db_session, organizacion.id) == []

    def test_sin_fila_de_configuracion_no_confirma_el_cliente(self, db_session: Session) -> None:
        """D4: no existe estado intermedio. Si la organización no tiene fila de
        configuración no hay a qué apuntar, y el bus tiene que revertir el
        cliente junto con la configuración, no confirmar uno sin la otra."""
        organizacion = _crear_organizacion(db_session, con_configuracion=False)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()

        with pytest.raises(ConfiguracionDeOrganizacionAusenteError):
            _procesar(
                db_session,
                _sobre(
                    tipo="CLIENTE_CONSUMIDOR_FINAL_CONFIGURAR",
                    organizacion_id=organizacion.id,
                    usuario_id=usuario_id,
                    dispositivo_id=dispositivo_id,
                    contenido={"nombre": "Consumidor final"},
                ),
                handler=clientes_commands.manejar_cliente_consumidor_final_configurar,
                contenido_cls=clientes_commands.ClienteConsumidorFinalConfigurarContenidoV1,
            )

        assert _clientes_de(db_session, organizacion.id) == [], (
            "La reversión del bus tiene que llevarse el cliente creado: un "
            "cliente marcado sin el par de configuración es exactamente el "
            "estado intermedio que D4 prohíbe."
        )


# --- listado: la búsqueda por texto con dígitos ---------------------------


class TestListadoContraElBus:
    def test_el_texto_con_digitos_encuentra_el_documento_normalizado(
        self, db_session: Session
    ) -> None:
        """El documento se guarda como `30111222`; el usuario escribe
        `30-111 222`. Si las dos condiciones del filtro se unieran con AND en
        vez de OR, esta búsqueda devolvería una lista vacía y no habría ningún
        error que lo delatara."""
        organizacion = _crear_organizacion(db_session)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(db_session, organizacion.id)
        db_session.commit()
        _crear(
            db_session,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            nombre="Kiosco Buscable",
            documento_tipo="DNI",
            documento_numero="30-111 222",
        )
        db_session.commit()

        for texto in ("30-111 222", "30111222", "30111"):
            encontrados, _cursor = clientes_repository.listar_clientes_paginado(
                organizacion.id, db_session, texto=texto
            )
            assert [c.nombre for c in encontrados] == ["Kiosco Buscable"], (
                f"La búsqueda por {texto!r} tiene que encontrar el cliente."
            )

    def test_el_listado_no_trae_clientes_de_otra_organizacion(self, db_session: Session) -> None:
        org_a = _crear_organizacion(db_session)
        org_b = _crear_organizacion(db_session)
        usuario_a, dispositivo_a = _crear_usuario_y_dispositivo(db_session, org_a.id)
        usuario_b, dispositivo_b = _crear_usuario_y_dispositivo(db_session, org_b.id)
        db_session.commit()
        _crear(
            db_session,
            organizacion_id=org_a.id,
            usuario_id=usuario_a,
            dispositivo_id=dispositivo_a,
            nombre="Compartido",
            codigo="MISMO-CODIGO",
        )
        _crear(
            db_session,
            organizacion_id=org_b.id,
            usuario_id=usuario_b,
            dispositivo_id=dispositivo_b,
            nombre="Compartido",
            codigo="MISMO-CODIGO",
        )
        db_session.commit()

        for organizacion in (org_a, org_b):
            encontrados, _cursor = clientes_repository.listar_clientes_paginado(
                organizacion.id, db_session, texto="Compartido"
            )
            assert len(encontrados) == 1, (
                "El mismo código y el mismo nombre en dos organizaciones no se "
                "contaminan: los índices son compuestos por `organizacion_id` (INV-02)."
            )

    def test_el_texto_no_trae_clientes_de_otra_organizacion_por_coincidencia(
        self, db_session: Session
    ) -> None:
        """El filtro por texto no puede saltarse el `organizacion_id` porque el
        texto coincida con un cliente ajeno."""
        org_a = _crear_organizacion(db_session)
        org_b = _crear_organizacion(db_session)
        usuario_a, dispositivo_a = _crear_usuario_y_dispositivo(db_session, org_a.id)
        db_session.commit()
        _crear(
            db_session,
            organizacion_id=org_a.id,
            usuario_id=usuario_a,
            dispositivo_id=dispositivo_a,
            nombre="Supermercado Del Valle",
            documento_tipo="DNI",
            documento_numero="30-111 222",
        )
        db_session.commit()

        encontrados, _cursor = clientes_repository.listar_clientes_paginado(
            org_b.id, db_session, texto="Supermercado"
        )
        assert encontrados == []
        encontrados, _cursor = clientes_repository.listar_clientes_paginado(
            org_b.id, db_session, texto="30-111 222"
        )
        assert encontrados == []


# --- CLI-06 activo desde el change 08 (D8) -----------------------------------


class TestReactivacionConMovimientos:
    """`CLIENTE_MODIFICAR` consulta a `cuentas_corrientes` si el cliente tiene
    movimientos (CLI-06, ADR-030, `design.md` D8 del change 08)."""

    def _cliente_con_estado(
        self, sesion: Session, *, estado: str, con_saldo_inicial: bool
    ) -> tuple[Any, UUID, UUID, UUID]:
        organizacion = _crear_organizacion(sesion)
        usuario_id, dispositivo_id = _crear_usuario_y_dispositivo(sesion, organizacion.id)
        sesion.commit()
        creado = _crear(
            sesion,
            organizacion_id=organizacion.id,
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
        )
        cliente_id = UUID(creado.resultado["cliente_id"])  # type: ignore[index]
        if con_saldo_inicial:
            cuentas_corrientes_service.registrar_saldo_inicial(
                organizacion.id,
                sesion,
                RELOJ,
                cuenta_tipo="CLIENTE",
                entidad_id=cliente_id,
                importe="150000.00",
                sentido="AUMENTA",
                occurred_at=MOMENTO,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                operation_id=uuid4(),
            )
        for siguiente in ("INACTIVO",) if estado == "INACTIVO" else ():
            self._modificar(
                sesion, organizacion.id, usuario_id, dispositivo_id, cliente_id, siguiente
            )
        sesion.commit()
        return organizacion, usuario_id, dispositivo_id, cliente_id

    def _modificar(
        self,
        sesion: Session,
        organizacion_id: UUID,
        usuario_id: UUID,
        dispositivo_id: UUID,
        cliente_id: UUID,
        estado: str,
    ) -> Comando:
        return _procesar(
            sesion,
            _sobre(
                tipo="CLIENTE_MODIFICAR",
                organizacion_id=organizacion_id,
                usuario_id=usuario_id,
                dispositivo_id=dispositivo_id,
                contenido=_ficha(cliente_id, estado=estado),
            ),
            handler=clientes_commands.manejar_cliente_modificar,
            contenido_cls=clientes_commands.ClienteModificarContenidoV1,
        )

    def test_reactivar_un_cliente_con_movimientos_se_rechaza(self, db_session: Session) -> None:
        organizacion, usuario_id, dispositivo_id, cliente_id = self._cliente_con_estado(
            db_session, estado="INACTIVO", con_saldo_inicial=True
        )

        with pytest.raises(ClienteConOperacionesError) as error:
            self._modificar(
                db_session, organizacion.id, usuario_id, dispositivo_id, cliente_id, "ACTIVO"
            )

        assert error.value.codigo == "CLIENTE_CON_OPERACIONES"
        assert _clientes_de(db_session, organizacion.id)[0].estado == "INACTIVO"

    def test_reactivar_un_cliente_inactivo_sin_movimientos_sigue_permitido(
        self, db_session: Session
    ) -> None:
        organizacion, usuario_id, dispositivo_id, cliente_id = self._cliente_con_estado(
            db_session, estado="INACTIVO", con_saldo_inicial=False
        )

        self._modificar(
            db_session, organizacion.id, usuario_id, dispositivo_id, cliente_id, "ACTIVO"
        )

        assert _clientes_de(db_session, organizacion.id)[0].estado == "ACTIVO"

    def test_un_cliente_con_movimientos_se_suspende_y_se_reactiva_si_nunca_estuvo_inactivo(
        self, db_session: Session
    ) -> None:
        """La consulta solo aplica a la salida de `INACTIVO` (CLI-06): con
        movimientos, `ACTIVO <-> SUSPENDIDO` sigue igual."""
        organizacion, usuario_id, dispositivo_id, cliente_id = self._cliente_con_estado(
            db_session, estado="ACTIVO", con_saldo_inicial=True
        )

        for estado in ("SUSPENDIDO", "ACTIVO", "INACTIVO"):
            self._modificar(
                db_session, organizacion.id, usuario_id, dispositivo_id, cliente_id, estado
            )

        assert _clientes_de(db_session, organizacion.id)[0].estado == "INACTIVO"

    def test_un_cliente_inactivo_con_movimientos_puede_seguir_inactivo_al_corregir_la_ficha(
        self, db_session: Session
    ) -> None:
        organizacion, usuario_id, dispositivo_id, cliente_id = self._cliente_con_estado(
            db_session, estado="INACTIVO", con_saldo_inicial=True
        )

        self._modificar(
            db_session, organizacion.id, usuario_id, dispositivo_id, cliente_id, "INACTIVO"
        )

        assert _clientes_de(db_session, organizacion.id)[0].estado == "INACTIVO"
