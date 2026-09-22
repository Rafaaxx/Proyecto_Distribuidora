"""Verificación de arranque: catálogo y registro de handlers deben
coincidir (`design.md` D3, change 04 tarea 4.5).

Se llama al arrancar la aplicación, después de importar todos los módulos
de negocio que declaran tipos y registran handlers (no en cada comando):
un tipo declarado sin handler, o un handler sin declarar, es un error de
programación que debe verse en el arranque, no descubrirse con un comando
real en producción (alternativa descartada de `design.md` D3).
"""

from __future__ import annotations

from app.commands import catalogo, registro


class CatalogoDesincronizadoError(RuntimeError):
    """El catálogo de tipos y el registro de handlers no coinciden."""


def verificar_catalogo_y_registro() -> None:
    # Acceso vía el módulo (no una importación directa del nombre) a
    # propósito: las pruebas unitarias reemplazan `registro._REGISTRO` con
    # `monkeypatch.setattr`, y una importación directa del nombre capturaría
    # el diccionario original en vez del que la prueba instaló.
    tipos_con_handler = {tipo for (tipo, _version) in registro._REGISTRO}
    tipos_en_catalogo = catalogo.tipos_declarados()

    declarados_sin_handler = tipos_en_catalogo - tipos_con_handler
    con_handler_sin_declarar = tipos_con_handler - tipos_en_catalogo

    if declarados_sin_handler or con_handler_sin_declarar:
        detalles: list[str] = []
        if declarados_sin_handler:
            detalles.append(
                f"declarados en el catálogo sin ningún handler registrado: "
                f"{sorted(declarados_sin_handler)}"
            )
        if con_handler_sin_declarar:
            detalles.append(
                f"con handler registrado sin declarar en el catálogo: "
                f"{sorted(con_handler_sin_declarar)}"
            )
        raise CatalogoDesincronizadoError("; ".join(detalles))
