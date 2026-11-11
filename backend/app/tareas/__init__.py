"""Tareas periódicas del sistema (change 28, `design.md` D2).

Un servicio aparte (`python -m app.tareas`) con la misma imagen del backend y su propia
credencial de base, `app_mantenimiento` (D3): verifica cada día que los saldos coincidan con sus
libros y borra los intentos de inicio de sesión de más de 24 horas. Usa los módulos de negocio
solo por su `service.py` (contrato `tareas-solo-por-service` de import-linter).
"""
