# Servicio de backups (change 27a, D10; docs/02 §16.2).
#
# Parte de la misma imagen que la base (postgres:17) para que `pg_dump` y `pg_restore` sean de
# la misma version que el servidor. Agrega tres scripts de shell, sin dependencias de terceros.
FROM postgres:17

COPY respaldar.sh salud.sh programar.sh retencion.sh lib_restaurar.sh restaurar.sh comprobar.sh \
     probar_restauracion.sh programar_prueba.sh salud_prueba.sh /opt/backup/

# Los scripts deben tener saltos de linea LF. Si el contexto se armo desde un clon de Windows
# con CRLF, esto los corrige (un CRLF rompe el shell con «bad interpreter»).
RUN sed -i 's/\r$//' /opt/backup/*.sh \
 && chmod 755 /opt/backup && chmod 644 /opt/backup/*.sh \
 && mkdir -p /estado-prueba && chown 999:999 /estado-prueba

# El servicio corre sin privilegios (compose: user 999:999, D11, change 27b): los scripts son
# legibles pero no escribibles por ese usuario, y el estado de salud va a /tmp (ESTADO_DIR).
#
# Sin argumentos: queda en marcha y hace el backup diario a BACKUP_HORA.
# Con `ahora`: hace un backup y termina (docker compose run --rm backup ahora).
ENTRYPOINT ["sh", "/opt/backup/programar.sh"]
