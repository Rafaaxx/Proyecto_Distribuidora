"""Catálogo de tipos de comando declarados (`02` §6.5, `design.md` D3).

Un tipo se declara una vez, indicando si admite modo `ONLINE` y/o `OFFLINE`
(`02` §6.2, §6.5) -- dato que necesitan los grupos 7 y 8 para rechazar un
comando en el modo que no le corresponde. La declaración es independiente
del registro de handlers por versión (`registro.py`): son dos listas que
cada módulo de negocio puebla juntas al definir su tipo de comando, y
`verificacion.verificar_catalogo_y_registro` exige que coincidan
exactamente.

No importa FastAPI ni SQLAlchemy: mecanismo puro (`design.md` D3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TipoDeComandoDeclarado:
    """Un tipo de comando declarado en el catálogo, con los modos que
    admite (`02` §6.5)."""

    tipo: str
    admite_online: bool
    admite_offline: bool
    permisos: tuple[str, ...] = ()
    """Los permisos que exige el tipo, para CUALQUIER modo (paso 4 de `02` §6.3, change 18b,
    `design.md` D23, ADR-056): alcanza con tener UNO. `ONLINE` sin ninguno -> `PERMISO_REQUERIDO`
    antes del handler; `OFFLINE` -> `PERMISO_REVOCADO` (SYN-10). Obligatorio y no vacío, salvo
    `sin_permiso`."""
    sin_permiso: str | None = None
    """La única salida: el tipo no exige permiso y dice por qué. Hoy ningún tipo la usa. Nunca en
    un tipo `OFFLINE`."""
    operacion_offline: OperacionObservable | None = None
    """La operación de negocio sobre la que el bus anota sus observaciones (`PERMISO_REVOCADO`).
    Sin declarar, la observación queda anotada sobre el comando mismo."""
    exige_credenciales_efimeras: bool = False
    """El tipo recibe SIEMPRE un secreto (PIN, contraseña) fuera del contenido, por clausura desde
    su ruta (change 18b, `design.md` D2 y D23, ADR-056). El lote lo rechaza en cualquier modo
    (`MODO_NO_ADMITIDO_PARA_TIPO`) y no lo guarda en cuarentena."""


@dataclass(frozen=True)
class OperacionObservable:
    """Dónde encuentra el bus el identificador de la operación de negocio que creó el handler:
    `tipo` (por ejemplo `"COBRANZA"`) y la clave del resultado del handler que lo trae (por
    ejemplo `"cobranza_id"`). Es lo que une una observación del bus con la operación que el
    usuario revisa (SYN-08)."""

    tipo: str
    clave_en_resultado: str


class TipoSinPermisosError(ValueError):
    """Un tipo no declaró los permisos que exige (ni la salida justificada `sin_permiso`), los
    declaró en blanco, declaró ambas cosas, o un tipo `OFFLINE` pretendió eximirse (error de
    programación, detectado al importar los módulos de negocio: la aplicación no arranca,
    `design.md` D23, SEG-06, ADR-056)."""


class TipoYaDeclaradoError(ValueError):
    """Dos declaraciones intentaron registrar el mismo tipo (error de
    programación, detectado al importar los módulos de negocio)."""


# Puebla el arranque de la aplicación importando los módulos de negocio que
# llaman a `declarar_tipo`. Las pruebas unitarias aíslan este diccionario
# con `monkeypatch` para no depender del orden de importación.
_CATALOGO: dict[str, TipoDeComandoDeclarado] = {}


def declarar_tipo(
    tipo: str,
    *,
    admite_online: bool,
    admite_offline: bool,
    permisos: tuple[str, ...] = (),
    sin_permiso: str | None = None,
    operacion_offline: OperacionObservable | None = None,
    exige_credenciales_efimeras: bool = False,
) -> TipoDeComandoDeclarado:
    """Declara `tipo` en el catálogo. Falla en el momento de la importación si el tipo ya estaba
    declarado, si no declara `permisos` (tupla no vacía, sin elementos en blanco) ni `sin_permiso`
    (justificación no vacía), si declara ambos, o si un tipo `OFFLINE` usa `sin_permiso`
    (change 18b, `design.md` D23, ADR-056)."""
    if tipo in _CATALOGO:
        raise TipoYaDeclaradoError(f"El tipo de comando {tipo!r} ya está declarado.")
    limpios = tuple(permiso.strip() for permiso in permisos)
    justificacion = None if sin_permiso is None else sin_permiso.strip() or None
    if limpios and sin_permiso is not None:
        raise TipoSinPermisosError(
            f"El tipo {tipo!r} declara `permisos` y `sin_permiso` a la vez (ADR-056)."
        )
    if limpios and not all(limpios):
        raise TipoSinPermisosError(f"El tipo {tipo!r} declara un permiso en blanco (ADR-056).")
    if sin_permiso is not None and justificacion is None:
        raise TipoSinPermisosError(f"El tipo {tipo!r} declara `sin_permiso` sin justificación.")
    if not limpios and justificacion is None:
        raise TipoSinPermisosError(
            f"El tipo {tipo!r} no declara `permisos` ni `sin_permiso` (SEG-06, ADR-056)."
        )
    if justificacion is not None and admite_offline:
        raise TipoSinPermisosError(
            f"El tipo {tipo!r} admite OFFLINE y no puede eximirse del permiso (SYN-10)."
        )
    declarado = TipoDeComandoDeclarado(
        tipo=tipo,
        admite_online=admite_online,
        admite_offline=admite_offline,
        permisos=limpios,
        sin_permiso=justificacion,
        operacion_offline=operacion_offline,
        exige_credenciales_efimeras=exige_credenciales_efimeras,
    )
    _CATALOGO[tipo] = declarado
    return declarado


def tipo_declarado(tipo: str) -> TipoDeComandoDeclarado | None:
    return _CATALOGO.get(tipo)


def tipos_declarados() -> frozenset[str]:
    return frozenset(_CATALOGO.keys())
