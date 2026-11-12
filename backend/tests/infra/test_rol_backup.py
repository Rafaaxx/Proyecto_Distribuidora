"""Rol de solo lectura del backup (change 27a, Lote 3; D11).

Specs `sistema/respaldos` («El rol de backup no puede escribir») y `sistema/despliegue`
(«La aplicacion sigue sin borrar libros»). Cita INV-05 y ADR-020. Postgres 17 real con los
scripts de produccion montados como en el compose.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

RAIZ = Path(__file__).resolve().parents[3]

LIBROS = ("cuenta_movimiento", "stock_movimiento", "costo_producto_mov", "auditoria")


def test_el_script_del_rol_usa_la_variable_sin_valor_por_defecto():
    texto = (RAIZ / "infra" / "postgres" / "20-init-backup-role.sh").read_text(encoding="utf-8")
    assert "APP_BACKUP_DB_PASSWORD:?" in texto
    assert "pg_read_all_data" in texto


CLAVE_BACKUP = "backup-solo-pruebas"
CLAVE_RUNTIME = "runtime-solo-pruebas"


def _motor(base, usuario, clave):
    return create_engine(base.url(usuario, clave))


def test_app_backup_lee_todas_las_tablas_incluidos_los_libros(base_migrada):
    motor = _motor(base_migrada, "app_backup", CLAVE_BACKUP)
    with motor.connect() as c:
        tablas = [
            f[0]
            for f in c.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        ]
        assert set(LIBROS) <= set(tablas)
        for tabla in tablas:
            c.execute(text(f'SELECT count(*) FROM "{tabla}"'))
        assert c.execute(text("SELECT count(*) FROM organizacion")).scalar_one() == 1
    motor.dispose()


@pytest.mark.parametrize(
    "sentencia",
    [
        "INSERT INTO organizacion (id, slug, nombre, moneda, zona_horaria, estado, actualizado_en) "
        "VALUES (gen_random_uuid(), 'x', 'x', 'ARS', 'UTC', 'ACTIVA', now())",
        "UPDATE organizacion SET nombre = 'otro'",
        "DELETE FROM auditoria",
        "CREATE TABLE intruso (id int)",
        "SELECT nextval('secuencia_de_prueba')",
    ],
)
def test_app_backup_no_puede_escribir(base_migrada, sentencia):
    motor = _motor(base_migrada, "app_backup", CLAVE_BACKUP)
    with pytest.raises(ProgrammingError), motor.begin() as c:
        c.execute(text(sentencia))
    motor.dispose()


def test_app_backup_no_es_superusuario_ni_miembro_de_escritura(base_migrada):
    motor = _motor(base_migrada, "app_backup", CLAVE_BACKUP)
    with motor.connect() as c:
        fila = c.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        assert tuple(fila) == (False, False, False)
        miembro_de = {
            f[0]
            for f in c.execute(
                text(
                    "SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid "
                    "WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
                )
            ).all()
        }
        assert miembro_de == {"pg_read_all_data"}
    motor.dispose()


def test_app_runtime_sigue_sin_delete_ni_update_sobre_auditoria(base_migrada):
    motor = _motor(base_migrada, "app_runtime", CLAVE_RUNTIME)
    for sentencia in ("DELETE FROM auditoria", "UPDATE auditoria SET id = id"):
        with pytest.raises(ProgrammingError), motor.begin() as c:
            c.execute(text(sentencia))
    motor.dispose()
