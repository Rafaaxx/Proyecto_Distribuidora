# Servicio de backups (change 27a, D10; docs/02 §16.2).
#
# Parte de la misma imagen que la base (postgres:17) para que `pg_dump` y `pg_restore` sean de
# la misma version que el servidor. Agrega tres scripts de shell, sin dependencias de terceros.
FROM postgres:17

COPY respaldar.sh salud.sh programar.sh /opt/backup/

# Los scripts deben tener saltos de linea LF. Si el contexto se armo desde un clon de Windows
# con CRLF, esto los corrige (un CRLF rompe el shell con «bad interpreter»).
RUN sed -i 's/\r$//' /opt/backup/*.sh

# Sin argumentos: queda en marcha y hace el backup diario a BACKUP_HORA.
# Con `ahora`: hace un backup y termina (docker compose run --rm backup ahora).
ENTRYPOINT ["sh", "/opt/backup/programar.sh"]
