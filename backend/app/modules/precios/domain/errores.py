"""Errores de dominio de `precios` (`design.md` D8, D9, `tasks.md` 3.3 y 4.1): código
estable, heredan de `DomainError` (`CLAUDE.md` §5). 422 para las validaciones de
contenido, 409 para los conflictos con el estado actual y 404 para lo que no existe en la
organización del token (INV-21, SEG-07)."""

from __future__ import annotations

from app.core.errors import DomainError


class CantidadBaseInvalidaError(DomainError):
    """La cantidad base de una línea no es un entero positivo (PRC-22, INV-04)."""

    codigo = "CANTIDAD_BASE_INVALIDA"
    status_http = 422


class UnidadesReferenciaInvalidasError(DomainError):
    """Las unidades de la presentación de referencia no son un entero `>= 1` (PRC-22,
    CAT-02, INV-04)."""

    codigo = "UNIDADES_REFERENCIA_INVALIDAS"
    status_http = 422


class MargenInvalidoError(DomainError):
    """El tipo o el valor de una regla de margen no es válido: valor negativo, con más de
    seis decimales, margen bruto `>= 1` (PRC-12) o fuera de `numeric(9,6)` (TR-02)."""

    codigo = "MARGEN_INVALIDO"
    status_http = 422


class AlcanceInvalidoError(DomainError):
    """El alcance de una regla es incoherente: `LISTA` con entidad, otro alcance sin ella o
    un tipo de alcance que no existe (PRC-13)."""

    codigo = "ALCANCE_INVALIDO"
    status_http = 422


class RedondeoInvalidoError(DomainError):
    """El múltiplo o la dirección de un redondeo no es válido: múltiplo no positivo, con más
    de dos decimales o fuera de `numeric(14,2)`, o una dirección que no es `ARRIBA`,
    `CERCANO` ni `ABAJO` (PRC-14, `design.md` D9)."""

    codigo = "REDONDEO_INVALIDO"
    status_http = 422


class PrecioNoPositivoError(DomainError):
    """El precio final es cero o negativo (por ejemplo, redondear hacia abajo un precio menor
    que el múltiplo): el producto no tiene precio (PRC-14, `design.md` D9)."""

    codigo = "PRECIO_NO_POSITIVO"
    status_http = 422


class ModoImpositivoNoSoportadoError(DomainError):
    """La organización tiene un modo impositivo para el que todavía no se generan precios:
    el modo `C` redondea el precio con IVA incluido y pertenece a la etapa 4 (PRC-15,
    `design.md` D9 punto 5)."""

    codigo = "MODO_IMPOSITIVO_NO_SOPORTADO"
    status_http = 422


class RecursoNoEncontradoError(DomainError):
    """Una lista, regla, categoría, producto, marca o proveedor que no existe en la
    organización del token (o que pertenece a otra) responde como inexistente (INV-21,
    SEG-07: "Un recurso de otra organización responde 404, no 403")."""

    codigo = "RECURSO_NO_ENCONTRADO"
    status_http = 404


class NombreInvalidoError(DomainError):
    """Nombre de lista vacío o solo espacios tras recortar (PRC-01, TR-10)."""

    codigo = "NOMBRE_INVALIDO"
    status_http = 422


class NombreDuplicadoError(DomainError):
    """Nombre de lista ya usado en la organización, sin distinguir mayúsculas
    (`ux_lista_precio__nombre`, `design.md` D13)."""

    codigo = "NOMBRE_DUPLICADO"
    status_http = 409


class ReglaDuplicadaError(DomainError):
    """La lista ya tiene una regla activa para ese alcance y esa entidad
    (`ux_regla_margen__alcance_activa`, `ux_regla_margen__lista_activa`, `design.md` D8)."""

    codigo = "REGLA_DUPLICADA"
    status_http = 409


class ListaInactivaError(DomainError):
    """Una lista inactiva no genera borradores ni publica versiones (PRC-01, `design.md` D4)."""

    codigo = "LISTA_INACTIVA"
    status_http = 409


class ListaEnUsoError(DomainError):
    """Una lista que es la predeterminada de la organización, o que está asignada a algún
    cliente que no está `INACTIVO`, no se desactiva (PRC-20, `design.md` D11)."""

    codigo = "LISTA_EN_USO"
    status_http = 409


class SinListaAplicableError(DomainError):
    """El cliente no tiene lista asignada activa y la organización no tiene una predeterminada
    activa: no hay lista con la que resolver el precio (PRC-20, VTA-10)."""

    codigo = "SIN_LISTA_APLICABLE"
    status_http = 409


class ListaSinVersionVigenteError(DomainError):
    """La lista no tiene una versión vigente en el momento pedido (PRC-03, PRC-20, VTA-10)."""

    codigo = "LISTA_SIN_VERSION_VIGENTE"
    status_http = 409


class ImporteInvalidoError(DomainError):
    """El precio fijado a mano no es un decimal exacto mayor que cero con a lo sumo dos
    decimales (TR-01, INV-03, `design.md` D7)."""

    codigo = "IMPORTE_INVALIDO"
    status_http = 422


class VersionNoEsBorradorError(DomainError):
    """La operación solo corresponde a una versión en `BORRADOR` y la versión ya está
    publicada o anulada: una versión publicada no cambia (PRC-04, INV-11, `01` §18)."""

    codigo = "VERSION_NO_ES_BORRADOR"
    status_http = 409


class ProductoInactivoError(DomainError):
    """Un producto inactivo no entra en una lista ni recibe un precio (CAT-05,
    `design.md` D7)."""

    codigo = "PRODUCTO_INACTIVO"
    status_http = 409


class CursorInvalidoError(DomainError):
    """El cursor de paginación no es uno que la API haya entregado."""

    codigo = "CURSOR_INVALIDO"
    status_http = 422


class VersionNoPublicadaError(DomainError):
    """Solo se anula una versión `PUBLICADA`: un borrador o una versión ya anulada no
    (PRC-05, `01` §18)."""

    codigo = "VERSION_NO_PUBLICADA"
    status_http = 409


class VersionYaVigenteError(DomainError):
    """Una versión cuya vigencia ya comenzó no se anula (PRC-05, PRC-04)."""

    codigo = "VERSION_YA_VIGENTE"
    status_http = 409


class VigenciaInvalidaError(DomainError):
    """La vigencia desde es anterior al momento de la publicación (nunca se publica hacia
    atrás, PRC-20) o la vigencia hasta no es posterior a la desde (PRC-02, `design.md` D6)."""

    codigo = "VIGENCIA_INVALIDA"
    status_http = 422


class VigenciaDuplicadaError(DomainError):
    """Otra versión publicada de la lista tiene la misma vigencia desde
    (`ux_lista_version__vigencia_desde`, PRC-03, `design.md` D6)."""

    codigo = "VIGENCIA_DUPLICADA"
    status_http = 409


class VersionSinPreciosError(DomainError):
    """Un borrador sin ningún precio no se publica (PRC-10, `design.md` D6)."""

    codigo = "VERSION_SIN_PRECIOS"
    status_http = 422
