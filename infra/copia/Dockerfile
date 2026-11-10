# Servicio de copia externa (change 27b, D2-D6, D11; docs/02 §16.2, §18).
#
# rclone con version FIJADA (cambiarla es una decision: se prueba antes). Sube a un almacenamiento
# externo los backups validos, cifrados en el equipo antes de salir (crypt de rclone), y los baja
# y descifra a pedido. Se configura solo con variables de entorno (lib.sh); no recibe ninguna
# credencial de la base. La regla de retencion es la MISMA de la imagen de backup
# (infra/backup/retencion.sh): por eso el contexto de construccion es `infra/`:
#   docker build -f infra/copia/Dockerfile infra
FROM rclone/rclone:1.68.2

# coreutils: `date -d` y `sort` de GNU (retencion.sh); tzdata: zona horaria de los nombres.
RUN apk add --no-cache coreutils tzdata \
 && mkdir -p /opt/copia /backups /bajados /destino-local

COPY backup/retencion.sh copia/lib.sh copia/copiar.sh copia/salud.sh /opt/copia/

# Saltos de linea LF (un CRLF rompe el shell) y permisos: los scripts se leen pero no se
# escriben; las carpetas de trabajo son del usuario sin privilegios (las montadas del equipo
# mandan con su propio dueño).
RUN sed -i 's/\r$//' /opt/copia/*.sh \
 && chmod 755 /opt/copia && chmod 644 /opt/copia/*.sh \
 && chown 999:999 /backups /bajados /destino-local

ENV HOME=/tmp
USER 999:999

# Sin argumentos: queda en marcha y copia cada hora.
# `ahora`: una copia y termina. `bajar <archivo>`: baja y descifra un backup del destino.
ENTRYPOINT ["sh", "/opt/copia/copiar.sh"]
