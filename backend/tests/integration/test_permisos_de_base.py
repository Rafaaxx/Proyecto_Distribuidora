"""Tarea 1.3 (change 28; D10): los privilegios REALES de la base migrada coinciden con la matriz
de `permisos_de_base.py`, tabla por tabla y rol por rol, y los roles de servicio no tienen
atributos de administracion (spec `sistema/permisos-de-base-de-datos`: sus tres requisitos y sus
ocho escenarios).

Se lee `pg_class.relacl` y `pg_attribute.attacl` (con `aclexplode`), no lo que dicen las
migraciones: un `GRANT` armado en un bucle o por columna tambien se ve. La matriz se prueba ademas
contra bases armadas a mano (un `DELETE` de mas, una tabla sin declarar) para que la verificacion
no pueda quedar muda.

Reglas citadas: INV-05 (los libros no admiten `UPDATE` ni `DELETE` de la aplicacion), ADR-018,
ADR-020 (si falta un `GRANT` o sobra un permiso, la CI falla), `02` §18.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import (
    NOMBRE_ROL_MANTENIMIENTO,
    NOMBRE_ROL_MIGRACIONES,
    NOMBRE_ROL_RUNTIME,
)
from permisos_de_base import (
    DUENO,
    LIBROS_SIN_UPDATE_NI_DELETE,
    MATRIZ,
    ROLES_DE_SERVICIO,
    SECUENCIAS_DECLARADAS,
    Entrada,
    PrivilegiosReales,
    borrados_sin_justificacion,
    comparar,
)
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import ProgrammingError

_TABLAS = text(
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
)
_ACL_DE_TABLA = text(
    "SELECT c.relname, r.rolname, a.privilege_type, a.is_grantable "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "CROSS JOIN LATERAL aclexplode(c.relacl) a "
    "JOIN pg_roles r ON r.oid = a.grantee "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND r.rolname = ANY(:roles)"
)
_ACL_DE_COLUMNA = text(
    "SELECT c.relname, at.attname, r.rolname, a.privilege_type "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "JOIN pg_attribute at ON at.attrelid = c.oid AND NOT at.attisdropped "
    "CROSS JOIN LATERAL aclexplode(at.attacl) a "
    "JOIN pg_roles r ON r.oid = a.grantee "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND r.rolname = ANY(:roles) "
    "AND at.attacl IS NOT NULL"
)


@pytest.fixture(scope="module")
def base(_engine_de_sesion: Engine) -> Iterator[Engine]:
    """La base migrada con los roles del entorno de produccion. El arnes crea `app_migrations`,
    `app_runtime` y `app_mantenimiento`; `app_backup` lo crea el script de produccion
    (`infra/postgres/20-init-backup-role.sh`) y se reproduce igual aca: miembro de
    `pg_read_all_data` y nada mas."""
    with _engine_de_sesion.begin() as conexion:
        conexion.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_backup') "
                "THEN CREATE ROLE app_backup LOGIN PASSWORD 'backup-solo-pruebas'; END IF; END $$"
            )
        )
        conexion.execute(text("GRANT pg_read_all_data TO app_backup"))
    yield _engine_de_sesion


def leer_privilegios(conexion: Connection) -> PrivilegiosReales:
    tablas = frozenset(conexion.execute(_TABLAS).scalars())
    roles = list(ROLES_DE_SERVICIO)
    tabla: dict[str, dict[str, set[str]]] = {rol: {} for rol in roles}
    con_opcion: dict[str, set[str]] = {rol: set() for rol in roles}
    for nombre, rol, privilegio, otorgable in conexion.execute(_ACL_DE_TABLA, {"roles": roles}):
        tabla[rol].setdefault(nombre, set()).add(privilegio)
        if otorgable:
            con_opcion[rol].add(nombre)
    columnas_update: dict[str, dict[str, set[str]]] = {rol: {} for rol in roles}
    otros: dict[str, dict[str, set[str]]] = {rol: {} for rol in roles}
    for nombre, columna, rol, privilegio in conexion.execute(_ACL_DE_COLUMNA, {"roles": roles}):
        destino = columnas_update if privilegio == "UPDATE" else otros
        destino[rol].setdefault(nombre, set()).add(columna)
    return PrivilegiosReales(
        tablas=tablas,
        tabla={r: {t: frozenset(p) for t, p in d.items()} for r, d in tabla.items()},
        columnas_update={
            r: {t: frozenset(c) for t, c in d.items()} for r, d in columnas_update.items()
        },
        otros_de_columna={r: {t: frozenset(c) for t, c in d.items()} for r, d in otros.items()},
        con_opcion_de_otorgar={r: frozenset(t) for r, t in con_opcion.items()},
    )


# --- requisito 1: los privilegios reales coinciden con la matriz -----------------------------


def test_inv05_los_privilegios_reales_coinciden_con_la_matriz_declarada(base: Engine) -> None:
    with base.connect() as conexion:
        diferencias = comparar(leer_privilegios(conexion))
    assert diferencias == []


def test_adr020_un_delete_de_mas_hace_fallar_nombrando_tabla_rol_y_privilegio(
    base: Engine,
) -> None:
    """Escenario «Un privilegio de más hace fallar la verificación»: una tabla de prueba a la que
    se le otorga DELETE a `app_runtime` sin declararlo en la matriz (se revierte al final)."""
    matriz = {**MATRIZ, "tabla_de_prueba": MATRIZ["categoria"]}
    with base.connect() as conexion, conexion.begin() as transaccion:
        conexion.execute(text("CREATE TABLE tabla_de_prueba (id int)"))
        conexion.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON tabla_de_prueba TO {NOMBRE_ROL_RUNTIME}")
        )
        diferencias = comparar(leer_privilegios(conexion), matriz)
        transaccion.rollback()
    assert diferencias == ["tabla_de_prueba: app_runtime tiene DELETE y la matriz no lo declara"]


def test_adr020_un_privilegio_que_falta_hace_fallar_nombrando_tabla_rol_y_privilegio(
    base: Engine,
) -> None:
    """Triangulacion: la diferencia inversa (la matriz declara algo que la base no otorga)."""
    matriz = {**MATRIZ, "tabla_de_prueba": MATRIZ["categoria"]}
    with base.connect() as conexion, conexion.begin() as transaccion:
        conexion.execute(text("CREATE TABLE tabla_de_prueba (id int)"))
        conexion.execute(text(f"GRANT SELECT, INSERT ON tabla_de_prueba TO {NOMBRE_ROL_RUNTIME}"))
        diferencias = comparar(leer_privilegios(conexion), matriz)
        transaccion.rollback()
    assert diferencias == ["tabla_de_prueba: app_runtime no tiene UPDATE y la matriz lo declara"]


def test_adr020_una_tabla_nueva_sin_declarar_hace_fallar_nombrando_la_tabla(base: Engine) -> None:
    """Escenario «Una tabla nueva sin declarar hace fallar la verificación»."""
    with base.connect() as conexion, conexion.begin() as transaccion:
        conexion.execute(text("CREATE TABLE tabla_sin_declarar (id int)"))
        diferencias = comparar(leer_privilegios(conexion))
        transaccion.rollback()
    assert diferencias == ["tabla_sin_declarar: tabla sin declarar en la matriz de permisos"]


def test_un_update_por_columna_de_mas_hace_fallar_nombrando_la_columna(base: Engine) -> None:
    matriz = {**MATRIZ, "tabla_de_prueba": MATRIZ["venta"]}
    with base.connect() as conexion, conexion.begin() as transaccion:
        conexion.execute(text("CREATE TABLE tabla_de_prueba (id int, estado text, total int)"))
        conexion.execute(text(f"GRANT SELECT, INSERT ON tabla_de_prueba TO {NOMBRE_ROL_RUNTIME}"))
        conexion.execute(
            text(f"GRANT UPDATE (estado, total) ON tabla_de_prueba TO {NOMBRE_ROL_RUNTIME}")
        )
        diferencias = comparar(leer_privilegios(conexion), matriz)
        transaccion.rollback()
    assert diferencias == [
        "tabla_de_prueba: app_runtime tiene UPDATE de la columna total y la matriz no lo declara"
    ]


def test_una_tabla_declarada_que_no_existe_hace_fallar(base: Engine) -> None:
    matriz = {**MATRIZ, "tabla_fantasma": MATRIZ["categoria"]}
    with base.connect() as conexion:
        diferencias = comparar(leer_privilegios(conexion), matriz)
    assert diferencias == ["tabla_fantasma: declarada en la matriz pero no existe en la base"]


def test_inv05_ningun_libro_admite_update_ni_delete_de_la_aplicacion(base: Engine) -> None:
    """Escenario «Ningún libro admite UPDATE ni DELETE de la aplicación»."""
    with base.connect() as conexion:
        reales = leer_privilegios(conexion)
    for libro in LIBROS_SIN_UPDATE_NI_DELETE:
        privilegios = reales.tabla[NOMBRE_ROL_RUNTIME].get(libro, frozenset())
        assert privilegios == {"SELECT", "INSERT"}, libro
        assert libro not in reales.columnas_update[NOMBRE_ROL_RUNTIME], libro


def test_cada_delete_declarado_tiene_su_justificacion_escrita() -> None:
    assert borrados_sin_justificacion() == []
    con_delete = {
        tabla
        for tabla, entrada in MATRIZ.items()
        if "DELETE" in entrada.runtime or "DELETE" in entrada.mantenimiento
    }
    # Los unicos DELETE de la etapa 1: tres de la aplicacion (borradores y asociaciones) y el de
    # la limpieza de intentos de login, que es del rol de mantenimiento y no de la aplicacion.
    assert con_delete == {"precio_item", "rol_permiso", "regla_descuento_alcance", "intento_login"}
    assert "DELETE" not in MATRIZ["intento_login"].runtime


def test_un_delete_sin_justificacion_o_una_justificacion_sin_delete_se_detecta() -> None:
    sin_texto = {
        **MATRIZ,
        "categoria": Entrada(tipo="maestra", runtime=frozenset({"SELECT", "DELETE"})),
    }
    assert borrados_sin_justificacion(sin_texto) == ["categoria: DELETE sin justificacion escrita"]
    de_mas = {
        **MATRIZ,
        "categoria": Entrada(
            tipo="maestra",
            runtime=frozenset({"SELECT"}),
            justificacion_delete="un texto largo que justifica un borrado que no existe en la base",
        ),
    }
    assert borrados_sin_justificacion(de_mas) == [
        "categoria: justificacion de un DELETE que la matriz no declara"
    ]


# --- requisito 2: atributos, duenos, PUBLIC y secuencias -------------------------------------


def test_los_roles_de_servicio_no_tienen_atributos_de_administracion(base: Engine) -> None:
    """Escenario «Atributos de los roles»."""
    with base.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, "
                "rolreplication, rolcanlogin FROM pg_roles WHERE rolname = ANY(:roles)"
            ),
            {"roles": list(ROLES_DE_SERVICIO)},
        ).all()
    assert {fila[0] for fila in filas} == set(ROLES_DE_SERVICIO)
    for rol, superusuario, crea_roles, crea_bases, salta_rls, replica, ingresa in filas:
        assert (superusuario, crea_roles, crea_bases, salta_rls, replica) == (
            False,
            False,
            False,
            False,
            False,
        ), rol
        assert ingresa is True, rol


def test_los_roles_de_servicio_no_son_miembros_de_otros_roles_salvo_el_de_backup(
    base: Engine,
) -> None:
    with base.connect() as conexion:
        membresias = conexion.execute(
            text(
                "SELECT m.member::regrole::text, r.rolname FROM pg_auth_members m "
                "JOIN pg_roles r ON r.oid = m.roleid WHERE m.member::regrole::text = ANY(:roles)"
            ),
            {"roles": list(ROLES_DE_SERVICIO)},
        ).all()
    assert {tuple(fila) for fila in membresias} == {("app_backup", "pg_read_all_data")}


def test_solo_app_migrations_es_dueno_de_las_tablas_las_secuencias_y_el_esquema(
    base: Engine,
) -> None:
    """Escenario «Dueños de los objetos»."""
    with base.connect() as conexion:
        duenos_de_objetos = conexion.execute(
            text(
                "SELECT DISTINCT pg_get_userbyid(c.relowner) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public'"
            )
        ).scalars()
        dueno_del_esquema = conexion.execute(
            text("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'")
        ).scalar_one()
    assert set(duenos_de_objetos) == {DUENO} == {NOMBRE_ROL_MIGRACIONES}
    assert dueno_del_esquema == DUENO


def test_public_no_tiene_privilegios_de_tabla_ni_create_en_el_esquema(base: Engine) -> None:
    """Escenario «PUBLIC no puede crear ni leer»."""
    with base.connect() as conexion:
        de_tabla = conexion.execute(
            text(
                "SELECT c.relname, a.privilege_type FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "CROSS JOIN LATERAL aclexplode(c.relacl) a "
                "WHERE n.nspname = 'public' AND a.grantee = 0"
            )
        ).all()
        del_esquema = (
            conexion.execute(
                text(
                    "SELECT a.privilege_type FROM pg_namespace n "
                    "CROSS JOIN LATERAL aclexplode(n.nspacl) a "
                    "WHERE n.nspname = 'public' AND a.grantee = 0"
                )
            )
            .scalars()
            .all()
        )
    assert de_tabla == []
    assert "CREATE" not in del_esquema


@pytest.mark.parametrize("rol", ROLES_DE_SERVICIO)
def test_ningun_rol_de_servicio_puede_crear_objetos_en_el_esquema(base: Engine, rol: str) -> None:
    with base.connect() as conexion:
        puede_crear = conexion.execute(
            text("SELECT has_schema_privilege(:rol, 'public', 'CREATE')"), {"rol": rol}
        ).scalar_one()
    assert puede_crear is False


def test_no_hay_secuencias_sin_declarar(base: Engine) -> None:
    """Las claves son UUID: una secuencia nueva obliga a declararla (y a decidir sus permisos)."""
    with base.connect() as conexion:
        secuencias = set(
            conexion.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'S'"
                )
            ).scalars()
        )
    assert secuencias == SECUENCIAS_DECLARADAS


# --- requisito 3: el rol de mantenimiento solo puede lo que sus tareas necesitan -------------


def test_app_backup_lee_todo_por_pg_read_all_data_y_no_tiene_acl_propio(base: Engine) -> None:
    with base.connect() as conexion:
        reales = leer_privilegios(conexion)
        sin_leer = [
            tabla
            for tabla in sorted(reales.tablas)
            if not conexion.execute(
                text("SELECT has_table_privilege('app_backup', :t, 'SELECT')"), {"t": tabla}
            ).scalar_one()
        ]
        escritura = [
            (tabla, privilegio)
            for tabla in sorted(reales.tablas)
            for privilegio in ("INSERT", "UPDATE", "DELETE", "TRUNCATE")
            if conexion.execute(
                text("SELECT has_table_privilege('app_backup', :t, :p)"),
                {"t": tabla, "p": privilegio},
            ).scalar_one()
        ]
    assert reales.tabla["app_backup"] == {}
    assert sin_leer == []
    assert escritura == []


@pytest.mark.parametrize(
    "sentencia",
    [
        "DELETE FROM auditoria",
        "DELETE FROM stock_movimiento",
        "UPDATE saldo_cuenta SET saldo = saldo",
        "INSERT INTO auditoria (id) VALUES (gen_random_uuid())",
        "DELETE FROM organizacion",
    ],
)
def test_inv05_app_mantenimiento_no_puede_tocar_un_libro_ni_un_saldo(
    base: Engine, app_mantenimiento_engine: Engine, sentencia: str
) -> None:
    """Escenario «El rol de mantenimiento no puede tocar un libro»: lo rechaza PostgreSQL."""
    with (
        pytest.raises(ProgrammingError, match="(?i)permission denied"),
        app_mantenimiento_engine.begin() as conexion,
    ):
        conexion.execute(text(sentencia))


def test_app_mantenimiento_borra_intentos_de_login(
    base: Engine, app_mantenimiento_engine: Engine
) -> None:
    """Escenario «El rol de mantenimiento borra intentos de inicio de sesión» (ADR-018)."""
    with base.begin() as conexion:
        conexion.execute(
            text(
                "INSERT INTO intento_login (id, ip, exito, creado_en) "
                "VALUES (gen_random_uuid(), '10.9.9.9', false, now())"
            )
        )
    with app_mantenimiento_engine.begin() as conexion:
        borradas = conexion.execute(text("DELETE FROM intento_login WHERE ip = '10.9.9.9'"))
    assert borradas.rowcount == 1


def test_el_rol_de_mantenimiento_declarado_es_el_de_la_matriz(base: Engine) -> None:
    """La matriz dice que `app_mantenimiento` lee 7 tablas, borra `intento_login` e inserta en
    `verificacion_consistencia`: nada mas."""
    declarado = {t: e.mantenimiento for t, e in MATRIZ.items() if e.mantenimiento}
    assert set(declarado) == {
        "organizacion",
        "saldo_cuenta",
        "cuenta_movimiento",
        "stock_saldo",
        "stock_movimiento",
        "costo_producto",
        "costo_producto_mov",
        "intento_login",
        "verificacion_consistencia",
    }
    assert NOMBRE_ROL_MANTENIMIENTO in ROLES_DE_SERVICIO
