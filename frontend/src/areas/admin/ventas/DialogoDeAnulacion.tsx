import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import {
  AMBITO_DE_ANULACION_DE_VENTA,
  devuelveDineroAEnviar,
  textoDeErrorDeAnulacion,
  textosDelEfectoEnCuenta,
} from '../../../domain/ventas/anulacion'
import { textoDeCantidadDeLinea } from '../../../domain/ventas/presentacion'
import { useMotivos } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { VentaAnularResultado, VentaDetalle } from '../../../features/ventas/api'
import { ErrorDeVentas } from '../../../features/ventas/errores'
import { useAnularVenta } from '../../../features/ventas/hooks'

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

export interface DialogoDeAnulacionProps {
  venta: VentaDetalle
  abierto: boolean
  alCerrar: () => void
  /** La venta se anuló: el detalle muestra el saldo que devolvió el comando. */
  alAnular: (resultado: VentaAnularResultado) => void
  /** `VENTA_YA_ANULADA`: otra persona la anuló antes; el detalle se vuelve a leer. */
  alYaAnulada: (mensaje: string) => void
}

/**
 * Diálogo de "Anular venta" (change 19, tarea 9.1; spec `administracion-de-ventas`, `design.md`
 * D16). Pide motivo (obligatorio), observación y, solo con cobranza confirmada, si se devuelve el
 * dinero (D2); en el consumidor final la devolución es fija (D3). Antes de confirmar muestra el
 * efecto con `domain/ventas/anulacion.ts`: el componente no calcula. Solo se monta con el
 * diálogo abierto: no pide los motivos hasta que el usuario elige anular.
 */
export function DialogoDeAnulacion({ venta, abierto, alCerrar, alAnular, alYaAnulada }: DialogoDeAnulacionProps) {
  return (
    <Dialogo abierto={abierto} titulo="Anular venta" onCerrar={alCerrar}>
      <FormularioDeAnulacion venta={venta} alCerrar={alCerrar} alAnular={alAnular} alYaAnulada={alYaAnulada} />
    </Dialogo>
  )
}

function FormularioDeAnulacion({
  venta,
  alCerrar,
  alAnular,
  alYaAnulada,
}: Pick<DialogoDeAnulacionProps, 'venta' | 'alCerrar' | 'alAnular' | 'alYaAnulada'>) {
  const { tiene } = usePermisos()
  const [motivoId, setMotivoId] = useState('')
  const [observacion, setObservacion] = useState('')
  const [eleccion, setEleccion] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const motivos = useMotivos(AMBITO_DE_ANULACION_DE_VENTA)
  const anular = useAnularVenta()

  const cobranza = venta.cobranza !== null && venta.cobranza.estado === 'CONFIRMADA' ? venta.cobranza : null
  const tieneCobranza = cobranza !== null
  const esConsumidorFinal = venta.cliente_es_consumidor_final
  const devuelveDinero = devuelveDineroAEnviar({ tieneCobranza, esConsumidorFinal, eleccion })
  const efecto = textosDelEfectoEnCuenta(venta.total, cobranza?.importe ?? null, devuelveDinero)
  const textoDeObservacion = observacion.trim() === '' ? null : observacion.trim()
  const faltaElegirDevolucion = tieneCobranza && devuelveDinero === null
  const operationId = useOperationIdPorContenido({
    ventaId: venta.venta_id,
    motivo_id: motivoId,
    observacion: textoDeObservacion,
    devuelve_dinero: devuelveDinero,
  })

  const confirmar = async () => {
    setError(null)
    try {
      const resultado = await anular.mutateAsync({
        ventaId: venta.venta_id,
        motivo_id: motivoId,
        observacion: textoDeObservacion,
        devuelve_dinero: devuelveDinero,
        operationId,
      })
      alCerrar()
      alAnular(resultado)
    } catch (e) {
      if (e instanceof ErrorDeVentas && e.codigo === 'VENTA_YA_ANULADA') {
        alCerrar()
        alYaAnulada(textoDeErrorDeAnulacion(e.codigo, e.message))
      } else {
        setError(
          e instanceof ErrorDeVentas
            ? textoDeErrorDeAnulacion(e.codigo, e.message)
            : 'No se pudo anular la venta. Revisá la conexión y reintentá: se reenvía la misma operación.',
        )
      }
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-col gap-1">
        <span className="flex items-center gap-1">
          <label htmlFor="anulacion-venta-motivo" className="text-sm font-medium text-primary">
            Motivo
          </label>
          <Ayuda clave="ventas.motivoAnulacion" />
        </span>
        <select
          id="anulacion-venta-motivo"
          className={CLASE_CONTROL}
          value={motivoId}
          onChange={(e) => setMotivoId(e.target.value)}
        >
          <option value="">Elegí un motivo</option>
          {(motivos.data?.items ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.nombre}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="anulacion-venta-observacion" className="text-sm font-medium text-primary">
          Observación (opcional)
        </label>
        <input
          id="anulacion-venta-observacion"
          className={CLASE_CONTROL}
          maxLength={500}
          value={observacion}
          onChange={(e) => setObservacion(e.target.value)}
        />
      </div>

      {tieneCobranza && esConsumidorFinal && (
        <p data-testid="devolucion-fija" className="flex items-center gap-1 text-sm text-primary">
          Al consumidor final siempre se le devuelve lo que pagó: no tiene cuenta donde dejarle saldo a favor.
          <Ayuda clave="ventas.consumidorFinalAnulacion" />
        </p>
      )}
      {tieneCobranza && !esConsumidorFinal && (
        <fieldset className="flex flex-col gap-1 text-sm text-primary">
          <legend className="flex items-center gap-1 font-medium">
            ¿Devolvés lo que cobraste?
            <Ayuda clave="ventas.devolverDinero" />
          </legend>
          <label className="flex items-center gap-2">
            <input type="radio" name="devuelve-dinero" checked={eleccion === true} onChange={() => setEleccion(true)} />
            Sí, devuelvo el dinero
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="devuelve-dinero" checked={eleccion === false} onChange={() => setEleccion(false)} />
            No, queda a favor del cliente
          </label>
        </fieldset>
      )}

      <div data-testid="reingreso-de-la-mercaderia" className="flex flex-col gap-1 text-sm text-primary">
        <span className="flex items-center gap-1 font-medium">
          La mercadería vuelve a {venta.ubicacion_nombre ?? venta.ubicacion_id}
          <Ayuda clave="ventas.reingresoUbicacion" />
          {tiene('VER_COSTOS') && <Ayuda clave="ventas.costoAnulacion" />}
        </span>
        <ul className="list-disc pl-5">
          {venta.lineas.map((linea) => (
            <li key={linea.linea_id}>
              {linea.producto_nombre ?? linea.producto_id}: {textoDeCantidadDeLinea(linea)}
            </li>
          ))}
        </ul>
      </div>

      {efecto.length > 0 && (
        <div data-testid="efecto-en-la-cuenta" className="flex flex-col gap-1 text-sm text-primary">
          {efecto.map((frase) => (
            <p key={frase}>{frase}</p>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <Boton
          variante="peligro"
          disabled={motivoId === '' || faltaElegirDevolucion || anular.isPending}
          onClick={() => void confirmar()}
        >
          Confirmar anulación
        </Boton>
        <Boton variante="secundario" onClick={alCerrar}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}
