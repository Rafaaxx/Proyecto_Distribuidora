/**
 * Formateo de fecha y hora para mostrar (tarea 14.5, corrección de la
 * verificación manual 13.5): usado por `CostosHistorialScreen.tsx` para
 * `creado_en` (momento de registro de un costo informado). Muestra la
 * hora LOCAL de quien mira la pantalla -- distinto de `vigencia_desde`
 * (una fecha de calendario, sin hora) y de la fecha de negocio de la
 * organización (`CostoVigenteResponse.fecha`, TR-04), que no dependen del
 * huso horario del navegador.
 */

function conDosDigitos(valor: number): string {
  return String(valor).padStart(2, '0')
}

/**
 * `momentoIso` es un `timestamptz` ISO 8601 (`creado_en` de la API).
 * Devuelve `dd/mm/aaaa hh:mm` en la zona horaria local del navegador.
 */
export function formatearFechaHora(momentoIso: string): string {
  const momento = new Date(momentoIso)
  const dia = conDosDigitos(momento.getDate())
  const mes = conDosDigitos(momento.getMonth() + 1)
  const anio = momento.getFullYear()
  const horas = conDosDigitos(momento.getHours())
  const minutos = conDosDigitos(momento.getMinutes())
  return `${dia}/${mes}/${anio} ${horas}:${minutos}`
}
