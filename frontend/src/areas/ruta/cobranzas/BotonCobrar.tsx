import { Link } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { AVISO_LO_YA_VENDIDO, textoDeJornadaNoAbierta } from '../../../domain/ruta/avisoDeJornada'
import { AVISO_DE_VERSION_MINIMA } from '../../../sync/versionMinima'
import { useJornadaNoAbierta } from '../datos/anulacion'
import { useVersionBloqueada } from '../datos/sincronizacion'
import { useSesionRutaActiva } from '../sesion/contextoSesion'

/**
 * Acceso a «Cobrar» del inicio y de la ficha (change 23, `design.md` D7, D8; RUT-09, `02` §6.6):
 * un enlace a la pantalla de cobro, o un botón deshabilitado con su motivo cuando la jornada ya no
 * está abierta o la aplicación está por debajo de la versión mínima. La cola se sigue enviando.
 * Cada motivo se omite (`false`) cuando la pantalla ya lo muestra: junto a «Vender» o en la
 * tarjeta de la jornada del inicio.
 */
const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'
const MOTIVO_SIN_JORNADA = 'Cobrar requiere una jornada abierta.'

export interface BotonCobrarProps {
  clienteId?: string
  /** Muestra el motivo de la jornada no abierta o sin jornada. */
  motivoDeJornada?: boolean
  /** Muestra el aviso de la versión mínima. */
  motivoDeVersion?: boolean
}

export function BotonCobrar({ clienteId, motivoDeJornada = true, motivoDeVersion = true }: BotonCobrarProps) {
  const { entrada } = useSesionRutaActiva()
  const jornadaNoAbierta = useJornadaNoAbierta()
  const versionBloqueada = useVersionBloqueada()
  const destino = clienteId === undefined ? '/ruta/cobrar' : `/ruta/cobrar?cliente=${clienteId}`

  const jornadaCortada = jornadaNoAbierta !== null && jornadaNoAbierta !== undefined
  if (!jornadaCortada && entrada.tipo !== 'sin_jornada' && !versionBloqueada) {
    return (
      <Link to={destino} className={CLASE_ENLACE}>
        Cobrar
      </Link>
    )
  }
  return (
    <div className="flex flex-col gap-1">
      <Boton variante="secundario" disabled>
        Cobrar
      </Boton>
      {motivoDeJornada && jornadaCortada && (
        <p className="flex flex-wrap items-center gap-1 text-sm text-primary/70">
          <span>{textoDeJornadaNoAbierta(jornadaNoAbierta.estado)}</span>
          <span>{AVISO_LO_YA_VENDIDO}</span>
          <Ayuda clave="ruta.jornadaNoAbierta" />
        </p>
      )}
      {motivoDeJornada && !jornadaCortada && entrada.tipo === 'sin_jornada' && (
        <p className="text-sm text-primary/70">{MOTIVO_SIN_JORNADA}</p>
      )}
      {motivoDeVersion && !jornadaCortada && entrada.tipo !== 'sin_jornada' && (
        <p className="flex items-center gap-1 text-sm text-primary/70">
          {AVISO_DE_VERSION_MINIMA}
          <Ayuda clave="ruta.versionMinima" />
        </p>
      )}
    </div>
  )
}
