"""Servicio de `descuentos` (`docs/02-arquitectura.md` §5.3): interfaz pública del módulo y casos
de uso de escritura de las reglas (`DSC-01` a `DSC-04`; `design.md` D15, D16, D19).

Los handlers de `descuentos/commands.py` llaman a las funciones de escritura; la venta (18b) y el
bootstrap (21) llaman a las de lectura y cálculo. Las funciones de escritura NO hacen `commit`
(lo gestiona el bus). Que los alcances existan en la organización se verifica por
`catalogo/service.py` (D19): una entidad inexistente o de otra organización responde 404."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.ids import nuevo_id
from app.modules.catalogo import service as catalogo_service
from app.modules.descuentos import repository
from app.modules.descuentos.domain import estados
from app.modules.descuentos.domain.errores import (
    DescuentoManualDeshabilitadoError,
    RecursoNoEncontradoError,
    ReglaDescuentoInvalidaError,
)
from app.modules.descuentos.domain.estados import validar_fin_de_vigencia
from app.modules.descuentos.domain.manual import Autorizador, ResultadoManual
from app.modules.descuentos.domain.manual import (
    evaluar_descuento_manual as _evaluar_descuento_manual,
)
from app.modules.descuentos.domain.manual import (
    rechazos_del_descuento_manual as _rechazos_del_descuento_manual,
)
from app.modules.descuentos.domain.motor import calcular_descuentos as _calcular_descuentos
from app.modules.descuentos.domain.reglas import AlcanceNuevo, ReglaValidada, validar_regla
from app.modules.descuentos.domain.tipos import (
    AlcanceRegla,
    DescuentoAplicado,
    LineaResultado,
    LineaVenta,
    ResultadoDescuentos,
)
from app.modules.descuentos.domain.tipos import ReglaDescuento as ReglaAplicable
from app.modules.descuentos.models import ReglaDescuento
from app.modules.identidad import service as identidad_service

__all__ = [
    "AlcanceRegla",
    "CambiosDeRegla",
    "DatosDeRegla",
    "DescuentoAplicado",
    "LineaResultado",
    "LineaVenta",
    "ReglaAplicable",
    "ResultadoManual",
    "ResultadoDescuentos",
    "activar_regla",
    "calcular_descuentos",
    "crear_regla",
    "evaluar_descuento_manual",
    "modificar_regla",
    "pausar_regla",
    "reglas_aplicables",
]


@dataclass(frozen=True)
class DatosDeRegla:
    """El contenido completo de una regla, tal como lo piden el alta y la edición de un
    borrador. `umbral`, `accion_valor` y `prioridad` llegan sin validar (`object`): la validación
    es de `domain/reglas.py`."""

    nombre: str
    tipo: str
    medida: str
    operador: str
    umbral: object
    accion_tipo: str
    accion_valor: object
    prioridad: object
    acumulable: bool
    alcances: Sequence[AlcanceNuevo]
    vigencia_desde: datetime | None
    vigencia_hasta: datetime | None


@dataclass(frozen=True)
class CambiosDeRegla:
    """Lo que trae `REGLA_DESCUENTO_MODIFICAR`: solo los campos informados (`campos`). Sobre un
    borrador se exige el contenido completo (reemplazo); sobre una regla activada o pausada solo
    se admite `vigencia_hasta` (D15)."""

    campos: frozenset[str]
    nombre: str | None = None
    tipo: str | None = None
    medida: str | None = None
    operador: str | None = None
    umbral: object = None
    accion_tipo: str | None = None
    accion_valor: object = None
    prioridad: object = None
    acumulable: bool | None = None
    alcances: Sequence[AlcanceNuevo] | None = None
    vigencia_desde: datetime | None = None
    vigencia_hasta: datetime | None = None


_OBLIGATORIOS_DE_BORRADOR = (
    "nombre",
    "tipo",
    "medida",
    "operador",
    "umbral",
    "accion_tipo",
    "accion_valor",
    "prioridad",
    "acumulable",
)


def _regla_para_actualizar(
    organizacion_id: UUID, regla_id: UUID, sesion: Session
) -> ReglaDescuento:
    """Toma el candado de la regla. Una regla inexistente, o de otra organización, responde
    igual (INV-21)."""
    regla = repository.obtener_regla_para_actualizar(organizacion_id, regla_id, sesion)
    if regla is None:
        raise RecursoNoEncontradoError(f"La regla {regla_id} no existe en esta organización.")
    return regla


def _validar_que_los_alcances_existen(
    organizacion_id: UUID, sesion: Session, alcances: Sequence[AlcanceNuevo]
) -> list[tuple[str, UUID]]:
    """Cada alcance debe ser un producto, una categoría o una marca de la organización
    (`catalogo/service.py`); si no, 404. Devuelve `(tipo, id)` con el id como `UUID`."""
    pares = [(alcance.tipo, UUID(str(alcance.entidad_id))) for alcance in alcances]
    consultas = {
        "PRODUCTO": catalogo_service.nombres_de_productos,
        "CATEGORIA": catalogo_service.nombres_de_categorias,
        "MARCA": catalogo_service.nombres_de_marcas,
    }
    for tipo, consulta in consultas.items():
        ids = {entidad for t, entidad in pares if t == tipo}
        if not ids:
            continue
        existentes = consulta(organizacion_id, ids, sesion)
        faltantes = ids - set(existentes)
        if faltantes:
            raise RecursoNoEncontradoError(
                f"El alcance {tipo} {sorted(faltantes, key=str)[0]} no existe en esta organización."
            )
    return pares


def _validar(datos: DatosDeRegla) -> ReglaValidada:
    return validar_regla(
        nombre=datos.nombre,
        tipo=datos.tipo,
        medida=datos.medida,
        operador=datos.operador,
        umbral=datos.umbral,
        accion_tipo=datos.accion_tipo,
        accion_valor=datos.accion_valor,
        prioridad=datos.prioridad,
        acumulable=datos.acumulable,
        alcances=datos.alcances,
        vigencia_desde=datos.vigencia_desde,
        vigencia_hasta=datos.vigencia_hasta,
    )


# --- REGLA_DESCUENTO_CREAR (DSC-01 a DSC-04) -----------------------------------------------


def crear_regla(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    datos: DatosDeRegla,
    actor_id: UUID | None,
) -> ReglaDescuento:
    """`REGLA_DESCUENTO_CREAR`: la regla nace en `BORRADOR` y no participa de ningún cálculo.
    Valida el contenido (`domain/reglas.py`) y que cada alcance exista en la organización (404);
    la regla y todos sus alcances se escriben en la misma transacción del bus (INV-01)."""
    validada = _validar(datos)
    alcances = _validar_que_los_alcances_existen(organizacion_id, sesion, validada.alcances)
    momento = reloj.now()
    regla = repository.crear_regla(
        organizacion_id,
        sesion,
        regla_id=nuevo_id(),
        nombre=validada.nombre,
        tipo=validada.tipo,
        medida=validada.medida,
        operador=validada.operador,
        umbral=validada.umbral,
        accion_tipo=validada.accion_tipo,
        accion_porcentaje=validada.accion_porcentaje,
        accion_importe=validada.accion_importe,
        prioridad=validada.prioridad,
        acumulable=validada.acumulable,
        vigencia_desde=validada.vigencia_desde,
        vigencia_hasta=validada.vigencia_hasta,
        estado=estados.BORRADOR,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    repository.insertar_alcances(
        organizacion_id, sesion, regla_id=regla.id, alcances=alcances, momento=momento
    )
    return regla


# --- REGLA_DESCUENTO_MODIFICAR (D15, D16) -----------------------------------------------------


def modificar_regla(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    regla_id: UUID,
    cambios: CambiosDeRegla,
    actor_id: UUID | None,
) -> ReglaDescuento:
    """`REGLA_DESCUENTO_MODIFICAR`. Con la regla bloqueada (`FOR UPDATE`) y su estado
    revalidado:

    - `BORRADOR`: reemplaza todos sus datos y sus alcances, con las validaciones del alta. El
      contenido tiene que venir completo (`REGLA_DESCUENTO_INVALIDA` si falta un campo
      obligatorio).
    - `ACTIVA` o `PAUSADA`: solo admite fijar o mover la vigencia hasta; cualquier otro campo
      (o ninguno) es `REGLA_NO_ES_BORRADOR` (D15). La regla conserva todos sus datos.
    """
    regla = _regla_para_actualizar(organizacion_id, regla_id, sesion)
    momento = reloj.now()

    if regla.estado != estados.BORRADOR:
        otros = cambios.campos - {"vigencia_hasta"}
        if otros or "vigencia_hasta" not in cambios.campos:
            estados.exigir_borrador(regla.estado)
        validar_fin_de_vigencia(regla.vigencia_desde, cambios.vigencia_hasta)
        return repository.fijar_vigencia_hasta(
            organizacion_id,
            sesion,
            regla,
            vigencia_hasta=cambios.vigencia_hasta,
            momento=momento,
            actualizado_por_id=actor_id,
        )

    faltantes = [campo for campo in _OBLIGATORIOS_DE_BORRADOR if campo not in cambios.campos]
    if faltantes:
        raise ReglaDescuentoInvalidaError(
            "Para corregir un borrador hay que enviar la regla completa; faltan: "
            f"{', '.join(faltantes)}."
        )
    validada = validar_regla(
        nombre=_requerido(cambios.nombre),
        tipo=_requerido(cambios.tipo),
        medida=_requerido(cambios.medida),
        operador=_requerido(cambios.operador),
        umbral=cambios.umbral,
        accion_tipo=_requerido(cambios.accion_tipo),
        accion_valor=cambios.accion_valor,
        prioridad=cambios.prioridad,
        acumulable=_requerido(cambios.acumulable),
        alcances=cambios.alcances or (),
        vigencia_desde=cambios.vigencia_desde,
        vigencia_hasta=cambios.vigencia_hasta,
    )
    alcances = _validar_que_los_alcances_existen(organizacion_id, sesion, validada.alcances)
    repository.reemplazar_datos_de_borrador(
        organizacion_id,
        sesion,
        regla,
        nombre=validada.nombre,
        tipo=validada.tipo,
        medida=validada.medida,
        operador=validada.operador,
        umbral=validada.umbral,
        accion_tipo=validada.accion_tipo,
        accion_porcentaje=validada.accion_porcentaje,
        accion_importe=validada.accion_importe,
        prioridad=validada.prioridad,
        acumulable=validada.acumulable,
        vigencia_desde=validada.vigencia_desde,
        vigencia_hasta=validada.vigencia_hasta,
        momento=momento,
        actualizado_por_id=actor_id,
    )
    repository.borrar_alcances_de_borrador(organizacion_id, sesion, regla_id)
    repository.insertar_alcances(
        organizacion_id, sesion, regla_id=regla_id, alcances=alcances, momento=momento
    )
    return regla


def _requerido[T](valor: T | None) -> T:
    """Un campo que `modificar_regla` ya comprobó presente (`campos`)."""
    if valor is None:
        raise ReglaDescuentoInvalidaError("Falta un campo obligatorio de la regla.")
    return valor


# --- REGLA_DESCUENTO_ACTIVAR y REGLA_DESCUENTO_PAUSAR (`01` §18) --------------------------


def activar_regla(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    regla_id: UUID,
    actor_id: UUID | None,
) -> ReglaDescuento:
    """`REGLA_DESCUENTO_ACTIVAR`: `BORRADOR → ACTIVA` y `PAUSADA → ACTIVA`. La vigencia desde
    queda definida (la que tenía o el momento de la activación, D16); una regla cuya vigencia ya
    terminó no se activa (`VIGENCIA_INVALIDA`). Con la regla bloqueada, una transición
    simultánea de otro usuario se revalida contra el estado que ella dejó."""
    regla = _regla_para_actualizar(organizacion_id, regla_id, sesion)
    momento = reloj.now()
    estado, desde = estados.activar(
        regla.estado, regla.vigencia_desde, regla.vigencia_hasta, momento
    )
    return repository.cambiar_estado(
        organizacion_id,
        sesion,
        regla,
        estado=estado,
        vigencia_desde=desde,
        momento=momento,
        actualizado_por_id=actor_id,
    )


def pausar_regla(
    organizacion_id: UUID,
    sesion: Session,
    reloj: Clock,
    *,
    regla_id: UUID,
    actor_id: UUID | None,
) -> ReglaDescuento:
    """`REGLA_DESCUENTO_PAUSAR`: `ACTIVA → PAUSADA`; cualquier otra es `REGLA_ESTADO_INVALIDO`."""
    regla = _regla_para_actualizar(organizacion_id, regla_id, sesion)
    estado = estados.pausar(regla.estado)
    return repository.cambiar_estado(
        organizacion_id,
        sesion,
        regla,
        estado=estado,
        vigencia_desde=regla.vigencia_desde,
        momento=reloj.now(),
        actualizado_por_id=actor_id,
    )


# --- lo que consumen la venta (18b) y el bootstrap (21) -----------------------------------------


def reglas_aplicables(
    organizacion_id: UUID, sesion: Session, momento: datetime
) -> list[ReglaAplicable]:
    """Las reglas `ACTIVA` vigentes en `momento` con sus alcances, listas para el motor (D20):
    excluye borradores, pausadas, programadas y vencidas. Usa el momento pedido (el de la
    operación, TR-05) y no el actual; filtra por la organización (INV-21). Una consulta de reglas
    y una de alcances, sin sumar nada en Python. Orden: prioridad y antigüedad."""
    reglas = repository.listar_reglas_aplicables(organizacion_id, momento, sesion)
    alcances = repository.listar_alcances(organizacion_id, [r.id for r in reglas], sesion)
    return [
        ReglaAplicable(
            id=str(regla.id),
            tipo=regla.tipo,  # type: ignore[arg-type]
            medida=regla.medida,  # type: ignore[arg-type]
            operador=regla.operador,  # type: ignore[arg-type]
            umbral=regla.umbral,
            accion_tipo=regla.accion_tipo,  # type: ignore[arg-type]
            accion_porcentaje=regla.accion_porcentaje,
            accion_importe=regla.accion_importe,
            acumulable=regla.acumulable,
            prioridad=regla.prioridad,
            alcances=tuple(
                AlcanceRegla(a.alcance_tipo, str(a.alcance_id))  # type: ignore[arg-type]
                for a in alcances[regla.id]
            ),
        )
        for regla in reglas
    ]


def calcular_descuentos(
    lineas: Sequence[LineaVenta],
    reglas: Sequence[ReglaAplicable],
    descuento_manual_general: Decimal | None,
) -> ResultadoDescuentos:
    """El motor de descuentos (`domain/motor.py`) sin tocar la base: recibe las líneas con su
    bruto ya calculado (cada una trae su `descuento_manual` propio o nulo), las reglas aplicables
    y el porcentaje manual general, y devuelve el detalle por línea y el
    `porcentaje_manual_maximo` que se compara contra el tope (D11, D12, D20)."""
    return _calcular_descuentos(lineas, reglas, descuento_manual_general)


def nombres_de_reglas(
    organizacion_id: UUID, regla_ids: set[UUID] | frozenset[UUID], sesion: Session
) -> dict[UUID, str]:
    """Nombre de cada regla de la organización pedida, por lote (change 18b, tarea 11.3: el
    detalle de la venta nombra la regla de cada descuento automático). Una regla de otra
    organización no figura (INV-21)."""
    return repository.nombres_de_reglas(organizacion_id, frozenset(regla_ids), sesion)


class _DatosDelManual(TypedDict):
    """Los argumentos que comparten `evaluar_descuento_manual` y `rechazos_del_descuento_manual`
    del dominio, salvo el `usuario_id`."""

    descuento_manual_habilitado: bool
    motivo_obligatorio: bool | None
    permisos_usuario: frozenset[str]
    tope_rol: Decimal
    tope_propio: Decimal | None
    porcentaje_maximo: Decimal
    motivo: str | None
    autorizador: Autorizador | None


def _datos_del_descuento_manual(
    organizacion_id: UUID,
    sesion: Session,
    *,
    usuario_id: UUID,
    porcentaje_maximo: Decimal,
    motivo: str | None,
    autorizador_id: UUID | None,
) -> _DatosDelManual:
    """Lo que `domain/manual.py` necesita, leído con los datos vigentes por `identidad`: la
    configuración, los permisos y el tope del usuario y los permisos del autorizador. Un usuario o
    un autorizador que no existe en la organización (o es de otra) no se encuentra (404,
    INV-21)."""
    configuracion = identidad_service.obtener_configuracion(organizacion_id, sesion)
    if configuracion is None:
        raise DescuentoManualDeshabilitadoError(
            "La organización no tiene configuración: el descuento manual no está habilitado."
        )
    usuario = identidad_service.obtener_datos_para_descuento_manual(
        organizacion_id, usuario_id, sesion
    )
    if usuario is None:
        raise RecursoNoEncontradoError(f"El usuario {usuario_id} no existe en esta organización.")

    autorizador = None
    if autorizador_id is not None:
        datos = identidad_service.obtener_datos_para_descuento_manual(
            organizacion_id, autorizador_id, sesion
        )
        if datos is None:
            raise RecursoNoEncontradoError(
                f"El autorizador {autorizador_id} no existe en esta organización."
            )
        autorizador = Autorizador(str(datos.usuario_id), datos.permisos)

    return _DatosDelManual(
        descuento_manual_habilitado=configuracion.descuento_manual_habilitado,
        motivo_obligatorio=configuracion.motivo_obligatorio_descuento,
        permisos_usuario=usuario.permisos,
        tope_rol=usuario.tope_rol,
        tope_propio=usuario.tope_propio,
        porcentaje_maximo=porcentaje_maximo,
        motivo=motivo,
        autorizador=autorizador,
    )


def rechazos_del_descuento_manual(
    organizacion_id: UUID,
    sesion: Session,
    *,
    usuario_id: UUID,
    porcentaje_maximo: Decimal,
    motivo: str | None,
    autorizador_id: UUID | None,
) -> list[str]:
    """Los códigos de TODOS los rechazos que el descuento manual tendría hoy (en el orden de
    D12), sin lanzar ninguno: lo usa la venta sin conexión, donde cada rechazo es una causa de
    `DESCUENTO_DIFIERE` (change 18b, D10 punto 4, SYN-05, INV-17). La evaluación con conexión es
    `evaluar_descuento_manual`, que rechaza con el primero. Solo lee."""
    datos = _datos_del_descuento_manual(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        porcentaje_maximo=porcentaje_maximo,
        motivo=motivo,
        autorizador_id=autorizador_id,
    )
    return [error.codigo for error in _rechazos_del_descuento_manual(**datos)]


def evaluar_descuento_manual(
    organizacion_id: UUID,
    sesion: Session,
    *,
    usuario_id: UUID,
    porcentaje_maximo: Decimal,
    motivo: str | None,
    autorizador_id: UUID | None,
) -> ResultadoManual:
    """Decide si el descuento manual de una venta se acepta, con qué tope y con qué resolución
    (DSC-06; `design.md` D12, D20). Se llama UNA vez por venta, con el
    `porcentaje_manual_maximo` que entregó el motor y solo si no es nulo. El servidor evalúa
    siempre con los datos vigentes, sin confiar en lo que el dispositivo haya decidido (TR-10).

    Resuelve por `identidad/service.py` la configuración de la organización, los permisos y el
    tope aplicable del usuario y los permisos del autorizador. Un usuario o un autorizador que no
    existe en la organización (o es de otra) no se encuentra (404, INV-21). SOLO LEE: no verifica
    ningún PIN, no escribe ninguna autorización y no audita (eso lo hace la venta, change 18b).
    Los identificadores del resultado son cadenas (`UUID` en su forma canónica)."""
    datos = _datos_del_descuento_manual(
        organizacion_id,
        sesion,
        usuario_id=usuario_id,
        porcentaje_maximo=porcentaje_maximo,
        motivo=motivo,
        autorizador_id=autorizador_id,
    )
    return _evaluar_descuento_manual(usuario_id=str(usuario_id), **datos)
