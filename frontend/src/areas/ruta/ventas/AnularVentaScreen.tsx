import { useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { AVISO_LO_YA_VENDIDO, textoDeJornadaNoAbierta } from '../../../domain/ruta/avisoDeJornada'
import { ErrorDeAnulacionLocal } from '../../../domain/ruta/anulacionLocal'
import {
  TEXTO_DE_ERROR_DE_ANULACION,
  validarFormularioDeAnulacion,
  type ErrorDeFormularioDeAnulacion,
} from '../../../domain/ruta/habilitacionDeAnulacion'
import { devuelveDineroAEnviar, textosDelEfectoEnCuenta } from '../../../domain/ventas/anulacion'
import { generarOperationId } from '../../../lib/api/operationId'
import { obtenerOGenerarDispositivoId } from '../../../lib/dispositivo/dispositivoId'
import { anularVentaLocal } from '../../../sync/anularVentaLocal'
import { APP_VERSION } from '../../../sync/appVersion'
import { dispararTrasVenta } from '../../../sync/disparadores'
import { motivoDeNoAnularDeDatos, useDatosParaAnular, type DatosParaAnular } from '../datos/anulacion'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-2 text-sm'
const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'

const TEXTO_NO_ANULABLE = 'Esta venta no se puede anular desde el teléfono.'
const MENSAJE_DE_FALLA = 'No se pudo guardar la anulación. Probá de nuevo.'

/**
 * Anular una venta desde el teléfono (change 22d, `design.md` D4, D5, D10; VTA-20, VTA-22,
 * VTA-24, CLI-03, INV-01, INV-06): motivo del ámbito, observación opcional, devolución de lo
 * cobrado si lo hubo, confirmación «¿Anular la venta {número}?» y una sola transacción local
 * (`anularVentaLocal`), con o sin señal. La anulación va siempre por la cola. Sin lógica de
 * negocio: las reglas viven en `domain/ruta/` y `sync/`.
 */
export function AnularVentaScreen() {
  const { id = '' } = useParams()
  const lectura = useDatosParaAnular(id)

  if (lectura.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (lectura.estado === 'no_encontrada') {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-primary">No encontramos esa venta en este teléfono.</p>
        <Link to="/ruta/ventas" className="text-sm underline">
          Ventas de hoy
        </Link>
      </div>
    )
  }

  const motivo = motivoDeNoAnularDeDatos(lectura)
  // Ya anulada (por ejemplo, recién confirmada): el detalle muestra la anulación.
  if (motivo === 'YA_ANULADA') return <Navigate to={`/ruta/ventas/${id}`} replace />
  if (motivo !== null) {
    return (
      <div className="flex flex-col gap-3">
        <Card className="flex flex-col gap-1 text-sm text-primary">
          <p>{TEXTO_NO_ANULABLE}</p>
          {motivo === 'JORNADA_NO_ABIERTA' && lectura.jornadaNoAbierta !== null && (
            <>
              <p className="flex items-center gap-1">
                {textoDeJornadaNoAbierta(lectura.jornadaNoAbierta.estado)}
                <Ayuda clave="ruta.jornadaNoAbierta" />
              </p>
              <p>{AVISO_LO_YA_VENDIDO}</p>
            </>
          )}
        </Card>
        <Link to={`/ruta/ventas/${id}`} className={CLASE_ENLACE}>
          Volver a la venta
        </Link>
      </div>
    )
  }
  return <FormularioDeAnulacion datos={lectura} />
}

function FormularioDeAnulacion({ datos }: { datos: DatosParaAnular }) {
  const navegar = useNavigate()
  const { venta } = datos
  const [motivoId, setMotivoId] = useState('')
  const [observacion, setObservacion] = useState('')
  const [eleccion, setEleccion] = useState<boolean | null>(null)
  const [errores, setErrores] = useState<ErrorDeFormularioDeAnulacion[]>([])
  const [confirmando, setConfirmando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [falla, setFalla] = useState<string | null>(null)
  // La misma operación en cada reintento y en el doble toque (INV-06).
  const operationId = useRef(generarOperationId())
  const enCurso = useRef(false)

  const tieneCobro = datos.cobrado !== null
  const devuelveDinero = devuelveDineroAEnviar({ tieneCobranza: tieneCobro, esConsumidorFinal: datos.esConsumidorFinal, eleccion })
  const efecto = textosDelEfectoEnCuenta(venta.calculo.total, datos.cobrado, devuelveDinero)

  const continuar = () => {
    const encontrados = validarFormularioDeAnulacion({
      motivoId,
      observacion,
      tieneCobro,
      esConsumidorFinal: datos.esConsumidorFinal,
      eleccion,
    })
    setErrores(encontrados)
    setFalla(null)
    if (encontrados.length === 0) setConfirmando(true)
  }

  const confirmar = async () => {
    if (enCurso.current) return
    enCurso.current = true
    setGuardando(true)
    setFalla(null)
    try {
      const motivo = datos.motivos.find((m) => m.id === motivoId)
      if (motivo === undefined) {
        setErrores(['MOTIVO_REQUERIDO'])
        setConfirmando(false)
        enCurso.current = false
        setGuardando(false)
        return
      }
      const dispositivoId = await obtenerOGenerarDispositivoId()
      const observacionLimpia = observacion.trim()
      await anularVentaLocal({
        ventaId: venta.venta_id,
        motivo: { id: motivo.id, nombre: motivo.nombre },
        observacion: observacionLimpia === '' ? null : observacionLimpia,
        devuelveDinero,
        operationId: operationId.current,
        usuarioId: datos.usuarioId,
        dispositivoId,
        ahora: new Date(),
        appVersion: APP_VERSION,
      })
      // D4: con o sin señal va por la cola; con señal se envía enseguida, como la venta.
      dispararTrasVenta()
      navegar(`/ruta/ventas/${venta.venta_id}`, { replace: true })
    } catch (error) {
      setConfirmando(false)
      setFalla(error instanceof ErrorDeAnulacionLocal && error.codigo === 'VENTA_NO_ANULABLE' ? TEXTO_NO_ANULABLE : MENSAJE_DE_FALLA)
      enCurso.current = false
      setGuardando(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold text-primary">Anular venta {venta.numero}</h1>
        <Ayuda clave="ruta.anularVenta" />
      </div>
      {falla !== null && <Alert>{falla}</Alert>}
      <Card className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <span className="flex items-center gap-1">
            <label htmlFor="anular-motivo" className="text-sm font-medium text-primary">
              Motivo
            </label>
            <Ayuda clave="ventas.motivoAnulacion" />
          </span>
          <select id="anular-motivo" className={CLASE_CONTROL} value={motivoId} onChange={(e) => setMotivoId(e.target.value)}>
            <option value="">Elegí un motivo</option>
            {datos.motivos.map((m) => (
              <option key={m.id} value={m.id}>
                {m.nombre}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="anular-observacion" className="text-sm font-medium text-primary">
            Observación (opcional)
          </label>
          <textarea
            id="anular-observacion"
            className={CLASE_CONTROL}
            rows={3}
            value={observacion}
            onChange={(e) => setObservacion(e.target.value)}
          />
        </div>

        {tieneCobro && datos.esConsumidorFinal && (
          <p data-testid="devolucion-fija" className="flex items-center gap-1 text-sm text-primary">
            Al consumidor final siempre se le devuelve lo que pagó: no tiene cuenta donde dejarle saldo a favor.
            <Ayuda clave="ventas.consumidorFinalAnulacion" />
          </p>
        )}
        {tieneCobro && !datos.esConsumidorFinal && (
          <fieldset className="flex flex-col gap-1 text-sm text-primary">
            <legend className="flex items-center gap-1 font-medium">
              ¿Devolvés lo que cobraste?
              <Ayuda clave="ventas.devolverDinero" />
            </legend>
            <label className="flex items-center gap-2 py-1">
              <input type="radio" name="devuelve-dinero" checked={eleccion === true} onChange={() => setEleccion(true)} />
              Sí, devuelvo el dinero
            </label>
            <label className="flex items-center gap-2 py-1">
              <input type="radio" name="devuelve-dinero" checked={eleccion === false} onChange={() => setEleccion(false)} />
              No, queda a favor del cliente
            </label>
          </fieldset>
        )}

        {efecto.length > 0 && (
          <div data-testid="efecto-en-la-cuenta" className="flex flex-col gap-1 text-sm text-primary">
            {efecto.map((frase) => (
              <p key={frase}>{frase}</p>
            ))}
          </div>
        )}

        {errores.length > 0 && (
          <Alert>
            {errores.map((e) => (
              <span key={e} className="block">
                {TEXTO_DE_ERROR_DE_ANULACION[e]}
              </span>
            ))}
          </Alert>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Boton variante="peligro" onClick={continuar}>
            Continuar
          </Boton>
          <Link to={`/ruta/ventas/${venta.venta_id}`} className={CLASE_ENLACE}>
            Volver
          </Link>
        </div>
      </Card>

      <Dialogo abierto={confirmando} titulo={`¿Anular la venta ${venta.numero}?`} onCerrar={() => setConfirmando(false)}>
        <div className="flex flex-col gap-3">
          <div className="flex justify-end gap-2">
            <Boton variante="secundario" disabled={guardando} onClick={() => setConfirmando(false)}>
              Cancelar
            </Boton>
            <Boton variante="peligro" disabled={guardando} onClick={() => void confirmar()}>
              Confirmar anulación
            </Boton>
          </div>
        </div>
      </Dialogo>
    </div>
  )
}

export default AnularVentaScreen
