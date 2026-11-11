/**
 * Datos fijos del escenario de aceptación (change 28, D14). Deben coincidir con la siembra
 * `python -m app.seed --escenario-aceptacion` (`backend/app/seed.py`). Contraseña y organización
 * de PRUEBA: solo existen en el entorno desechable de aceptación.
 */
export const ORGANIZACION = 'organizacion-inicial'
export const SEGUNDA_ORGANIZACION = 'organizacion-dos'
export const CONTRASENA = 'Aceptacion-2026'
/** PIN de 6 dígitos que se define la primera vez que un usuario entra a `/ruta` desde un dispositivo. */
export const PIN_DE_PRUEBA = '482915'

export type NombreDeUsuario =
  | 'admin'
  | 'administracion'
  | 'ges01'
  | 'consulta'
  | 'supervisor'
  | 'sup01'
  | 'vendedor'
  | 'vendedor2'
