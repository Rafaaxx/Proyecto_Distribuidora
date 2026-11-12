import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import type { NotaVentaConfig } from '../../../features/configuracion/api'
import { ErrorDeConfiguracion } from '../../../features/configuracion/errores'
import { useConfigurarNotaVenta, useNotaVentaConfig } from '../../../features/configuracion/useNotaVenta'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'

const TITULO = 'Nota de venta'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MENSAJE_DE_RED = 'No se pudo guardar. Podés reintentar: se reenvía la misma operación.'
const CODIGO_DATO_INVALIDO = 'DATO_DE_NOTA_INVALIDO'

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      <p className="text-sm text-primary/70">No tenés permiso para cambiar la configuración de la empresa.</p>
    </main>
  )
}

/** El servidor nombra el campo en el mensaje (no devuelve un campo aparte): domicilio o teléfono. */
function campoDelError(error: unknown): 'domicilio' | 'telefono' | null {
  if (!(error instanceof ErrorDeConfiguracion) || error.codigo !== CODIGO_DATO_INVALIDO) return null
  return /tel[eé]fono/i.test(error.message) ? 'telefono' : 'domicilio'
}

function mensajeGeneral(error: unknown): string | null {
  if (error === null || error === undefined || campoDelError(error) !== null) return null
  return error instanceof ErrorDeConfiguracion ? error.message : MENSAJE_DE_RED
}

/**
 * Parámetros de la nota de venta (change 20, tarea 7.3; spec `parametros-de-organizacion`; VTA-13,
 * AUD-01; D3, D4, D10): mostrar el saldo, domicilio y teléfono. Solo con `ADMIN_CONFIGURACION`
 * (ADR-027: sin el permiso no se monta ni pide nada). El largo lo valida el servidor (TR-10).
 */
export function NotaDeVentaScreen() {
  return (
    <SiTienePermiso permiso="ADMIN_CONFIGURACION" fallback={<SinPermiso />}>
      <Contenido />
    </SiTienePermiso>
  )
}

function Contenido() {
  const configuracion = useNotaVentaConfig()
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      {configuracion.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
      {configuracion.isError && <Alert>No se pudo obtener la configuración.</Alert>}
      {configuracion.isSuccess && <Bloque actual={configuracion.data} />}
    </main>
  )
}

function Bloque({ actual }: { actual: NotaVentaConfig }) {
  const [muestraSaldo, setMuestraSaldo] = useState(actual.muestra_saldo)
  const [domicilio, setDomicilio] = useState(actual.domicilio ?? '')
  const [telefono, setTelefono] = useState(actual.telefono ?? '')
  const [guardado, setGuardado] = useState(false)
  const configurar = useConfigurarNotaVenta()

  const sinCambios =
    muestraSaldo === actual.muestra_saldo && domicilio === (actual.domicilio ?? '') && telefono === (actual.telefono ?? '')

  const guardar = async (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    setGuardado(false)
    try {
      await configurar.mutateAsync({
        muestra_saldo: muestraSaldo,
        domicilio: domicilio.trim() === '' ? null : domicilio,
        telefono: telefono.trim() === '' ? null : telefono,
      })
      setGuardado(true)
    } catch {
      // El error queda en `configurar.error` y se muestra junto al campo o abajo.
    }
  }
  const campo = campoDelError(configurar.error)
  const error = mensajeGeneral(configurar.error)
  const mensajeDelCampo = configurar.error instanceof Error ? configurar.error.message : undefined

  return (
    <Card className="flex flex-col gap-3">
      <form onSubmit={(evento) => void guardar(evento)} className="flex flex-col gap-3" data-testid="bloque-nota-de-venta">
        <div className="flex items-center gap-1">
          <label className="flex items-center gap-2 text-sm text-primary">
            <input type="checkbox" checked={muestraSaldo} onChange={(evento) => setMuestraSaldo(evento.target.checked)} />
            Mostrar el saldo de la cuenta en la nota
          </label>
          <Ayuda clave="configuracion.notaMuestraSaldo" />
        </div>
        <div className="flex items-center gap-1">
          <h2 className="text-base font-semibold text-primary">Encabezado de la nota</h2>
          <Ayuda clave="configuracion.notaDatosOrganizacion" />
        </div>
        <div data-testid="campo-domicilio">
          <Campo id="nota-domicilio" etiqueta="Domicilio" error={campo === 'domicilio' ? mensajeDelCampo : undefined}>
            <input
              id="nota-domicilio"
              className={`${CLASE_CONTROL} w-full max-w-md`}
              value={domicilio}
              onChange={(evento) => setDomicilio(evento.target.value)}
            />
          </Campo>
        </div>
        <div data-testid="campo-telefono">
          <Campo id="nota-telefono" etiqueta="Teléfono" error={campo === 'telefono' ? mensajeDelCampo : undefined}>
            <input
              id="nota-telefono"
              className={`${CLASE_CONTROL} w-full max-w-xs`}
              value={telefono}
              onChange={(evento) => setTelefono(evento.target.value)}
            />
          </Campo>
        </div>
        {error && <Alert>{error}</Alert>}
        {guardado && !error && campo === null && (
          <p role="status" className="text-sm text-primary">
            Se guardó la configuración de la nota de venta.
          </p>
        )}
        <div>
          <Boton type="submit" disabled={sinCambios || configurar.isPending}>
            Guardar nota de venta
          </Boton>
        </div>
      </form>
    </Card>
  )
}

export default NotaDeVentaScreen
