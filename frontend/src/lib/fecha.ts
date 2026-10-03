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

/**
 * Igual que `formatearFechaHora` pero en la zona horaria pasada (IANA, por
 * ejemplo `America/Argentina/Mendoza`) en vez de la del navegador: las fechas
 * del estado de cuenta se muestran en la zona de la organización (change 08,
 * TR-04). Formato `dd/mm/aaaa hh:mm`, hora de 24 h.
 */
export function formatearFechaHoraEnZona(momentoIso: string, zonaHoraria: string): string {
  const partes = new Intl.DateTimeFormat('en-GB', {
    timeZone: zonaHoraria,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(momentoIso))
  const valor = (tipo: Intl.DateTimeFormatPartTypes): string => partes.find((parte) => parte.type === tipo)?.value ?? ''
  return `${valor('day')}/${valor('month')}/${valor('year')} ${valor('hour')}:${valor('minute')}`
}

/**
 * Fecha de negocio `aaaa-mm-dd` (TR-04, sin hora ni zona) como `dd/mm/aaaa`. Manipula la
 * cadena: pasar por `Date` correría el día según la zona del navegador.
 */
export function formatearFechaDeNegocio(fecha: string): string {
  const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fecha)
  return partes ? `${partes[3] ?? ''}/${partes[2] ?? ''}/${partes[1] ?? ''}` : fecha
}
