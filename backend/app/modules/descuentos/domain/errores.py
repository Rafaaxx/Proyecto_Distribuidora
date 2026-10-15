"""Errores de dominio del motor de descuentos: código estable, heredan de `DomainError`
(`CLAUDE.md` §5). 422: la entrada del cálculo no es válida."""

from __future__ import annotations

from app.core.errors import DomainError


class DescuentoManualInvalidoError(DomainError):
    """El porcentaje de descuento manual, general o propio de una línea, no es una fracción de
    hasta 6 decimales mayor que 0 y hasta 1, o llegó como punto flotante (DSC-06, TR-02, INV-03;
    `design.md` D11, D11.1: un propio de 0 no excluye la línea)."""

    codigo = "DESCUENTO_MANUAL_INVALIDO"
    status_http = 422


class LineaDescuentoInvalidaError(DomainError):
    """Una línea de la venta no sirve para calcular descuentos: bruto negativo o con más de dos
    decimales, cantidad base o unidades de referencia que no son enteros positivos (INV-04,
    PRC-22)."""

    codigo = "LINEA_DESCUENTO_INVALIDA"
    status_http = 422


class ReglaDescuentoInvalidaError(DomainError):
    """Una regla entregada al motor está mal formada: tipo, medida, operador o acción fuera de
    las listas cerradas de DSC-02 a DSC-04, o valor de la acción fuera de dominio. Las reglas
    guardadas ya pasaron por `domain/reglas.py`; esta es la última guardia del motor."""

    codigo = "REGLA_DESCUENTO_INVALIDA"
    status_http = 422


class UmbralInvalidoError(DomainError):
    """El umbral no es positivo o no respeta la medida: entero en unidades base, hasta cuatro
    decimales en cajas, hasta dos en importe (DSC-03, INV-04, TR-01; `design.md` D5)."""

    codigo = "UMBRAL_INVALIDO"
    status_http = 422


class AccionInvalidaError(DomainError):
    """El valor de la acción está fuera de dominio: un porcentaje mayor que 0 y hasta 1 con hasta
    seis decimales, o un importe mayor que 0 con hasta dos (DSC-04, TR-02, INV-03)."""

    codigo = "ACCION_INVALIDA"
    status_http = 422


class PrioridadInvalidaError(DomainError):
    """La prioridad no es un entero mayor o igual que 1 (DSC-01; `design.md` D8)."""

    codigo = "PRIORIDAD_INVALIDA"
    status_http = 422


class NombreInvalidoError(DomainError):
    """El nombre de la regla queda vacío después de recortarlo (DSC-01)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class AlcanceInvalidoError(DomainError):
    """Los alcances no son coherentes con el tipo de regla: una regla de operación no tiene
    alcances, una de alcance tiene al menos uno, sin repetidos (DSC-02; `03` §11)."""

    codigo = "ALCANCE_INVALIDO"
    status_http = 422


class VigenciaInvalidaError(DomainError):
    """La vigencia hasta no es posterior a la desde, o se intenta activar una regla cuya vigencia
    ya terminó (DSC-01; `design.md` D16)."""

    codigo = "VIGENCIA_INVALIDA"
    status_http = 422


class ReglaEstadoInvalidoError(DomainError):
    """La transición pedida no existe en la máquina `BORRADOR → ACTIVA ↔ PAUSADA`; la regla queda
    como estaba (`01` §18, DSC-01)."""

    codigo = "REGLA_ESTADO_INVALIDO"
    status_http = 409


class ReglaNoEsBorradorError(DomainError):
    """Una regla activada o pausada no se edita: se la pausa y se crea otra, salvo el cambio de su
    vigencia hasta (TR-06; `design.md` D15)."""

    codigo = "REGLA_NO_ES_BORRADOR"
    status_http = 409


class RecursoNoEncontradoError(DomainError):
    """Una regla, producto, categoría o marca que no existe en la organización del token (o que
    pertenece a otra) responde como inexistente (INV-21, SEG-07: 404, no 403)."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class CursorInvalidoError(DomainError):
    """El cursor de paginación no es uno que la API haya entregado."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class DescuentoManualDeshabilitadoError(DomainError):
    """La organización no tiene habilitado el descuento manual (DSC-06; `01` §4)."""

    codigo = "DESCUENTO_MANUAL_DESHABILITADO"
    status_http = 409


class MotivoRequeridoError(DomainError):
    """La organización exige motivo en el descuento manual y no se indicó uno (`01` §4, DSC-08;
    `design.md` D14: con el parámetro sin definir, el motivo no es obligatorio)."""

    codigo = "MOTIVO_REQUERIDO"
    status_http = 422


class AutorizacionRequeridaError(DomainError):
    """El mayor porcentaje manual de la venta supera el tope aplicable y no hay quien autorice
    (DSC-06; `design.md` D12)."""

    codigo = "AUTORIZACION_REQUERIDA"
    status_http = 403


class AutorizadorSinPermisoError(DomainError):
    """El autorizador indicado no tiene `AUTORIZAR_DESCUENTO` (DSC-06, SEG-06)."""

    codigo = "AUTORIZADOR_SIN_PERMISO"
    status_http = 403
