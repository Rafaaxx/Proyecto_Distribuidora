import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import { formatearCantidad, referenciaDeRespuesta, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import {
  armarDevolucion,
  precargarDevolucion,
  textoDeDevolucion,
  totalDeDevolucion,
  type DevolucionDeCierre,
  type FilaDeDevolucion,
} from '../../../domain/stock/rendicion'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import type { CierreResultado } from '../../../features/stock/api'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../features/stock/errores'
import { useProductosParaRendicion, useResumenDeJornada, useSaldosCompletos, useUbicaciones } from '../../../features/stock/hooks'
import { AVISO_REQUIERE_CONEXION, CLASE_CONTROL } from './piezasDeOperacion'
import { CampoDeCantidad } from './piezasDeRendicion'

/** Lo que el detalle muestra después de cerrar con devolución: el enlace a la transferencia. */
export interface DevolucionRealizada {
  transferenciaId: string
  texto: string
}

export interface CierreDeJornadaDialogoProps {
  abierto: boolean
  jornadaId: string
  ubicacionId: string
  ubicacionNombre: string
  /** `TRANSFERIR_STOCK`: sin él no se ofrece devolver el remanente (el servidor lo exige igual). */
  puedeDevolver: boolean
  onCerrar: () => void
  onConfirmar: (devolucion: DevolucionDeCierre | null, operationId: string) => Promise<CierreResultado>
  onCerrada: (devolucion: DevolucionRealizada | null) => void
  /** El servidor dijo que la jornada ya no está en rendición: el detalle se vuelve a leer. */
  onEstadoInvalido: () => void
}

/**
 * «Cerrar jornada» (change 24, tarea 13.1; `design.md` D6, D9; RUT-08, STK-07): el aviso de cierre y,
 * con `TRANSFERIR_STOCK`, «Devolver el remanente a» un depósito activo. Al elegir el destino las
 * líneas se precargan con todo lo contado (o, sin conteo, con el stock actual) y se pueden editar.
 * La devolución es una transferencia común; el reintento reenvía el mismo `operation_id`.
 */
export function CierreDeJornadaDialogo({ abierto, ...resto }: CierreDeJornadaDialogoProps) {
  return (
    <Dialogo abierto={abierto} titulo="Cerrar jornada" onCerrar={resto.onCerrar}>
      <Formulario {...resto} />
    </Dialogo>
  )
}

function Formulario({
  jornadaId,
  ubicacionId,
  ubicacionNombre,
  puedeDevolver,
  onCerrar,
  onConfirmar,
  onCerrada,
  onEstadoInvalido,
}: Omit<CierreDeJornadaDialogoProps, 'abierto'>) {
  const [destino, setDestino] = useState<{ id: string; nombre: string }>({ id: '', nombre: '' })
  const [filas, setFilas] = useState<FilaDeDevolucion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const resultado = armarDevolucion(destino.id, filas ?? [])
  const operationId = useOperationIdPorContenido({ jornadaId, devolucion: resultado.ok ? resultado.devolucion : null })
  const productosATransferir = resultado.ok ? (resultado.devolucion?.lineas.length ?? 0) : 0

  const confirmar = async () => {
    if (!resultado.ok) {
      setError(resultado.mensaje)
      return
    }
    setError(null)
    setEnviando(true)
    try {
      const cierre = await onConfirmar(resultado.devolucion, operationId)
      onCerrada(
        cierre.transferencia_id
          ? { transferenciaId: cierre.transferencia_id, texto: textoDeDevolucion(productosATransferir, destino.nombre) }
          : null,
      )
      onCerrar()
    } catch (falla) {
      setError(mensajeDeErrorDeStock(falla, 'jornada'))
      if (falla instanceof ErrorDeStock && falla.codigo === 'JORNADA_ESTADO_INVALIDO') onEstadoInvalido()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-primary">Vas a cerrar la jornada de {ubicacionNombre} y liberar la ubicación.</p>
      <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>
      {error && <Alert>{error}</Alert>}

      {puedeDevolver && (
        <DevolverElRemanente
          jornadaId={jornadaId}
          ubicacionId={ubicacionId}
          destino={destino}
          filas={filas}
          productosATransferir={productosATransferir}
          onDestino={(nuevo, precarga) => {
            setDestino(nuevo)
            setError(null)
            if (precarga !== null) setFilas(precarga)
          }}
          onFilas={setFilas}
        />
      )}

      <div className="flex gap-2">
        <Boton disabled={enviando} onClick={() => void confirmar()}>
          Confirmar
        </Boton>
        <Boton variante="secundario" onClick={onCerrar}>
          Cancelar
        </Boton>
      </div>
    </div>
  )
}

interface DevolverElRemanenteProps {
  jornadaId: string
  ubicacionId: string
  destino: { id: string; nombre: string }
  filas: FilaDeDevolucion[] | null
  productosATransferir: number
  /** `precarga` solo viene la primera vez que se elige un destino. */
  onDestino: (destino: { id: string; nombre: string }, precarga: FilaDeDevolucion[] | null) => void
  onFilas: (actualizar: (actual: FilaDeDevolucion[] | null) => FilaDeDevolucion[]) => void
}

/** Las lecturas de esta parte (resumen, saldos, ubicaciones) solo se piden con `TRANSFERIR_STOCK`. */
function DevolverElRemanente({ jornadaId, ubicacionId, destino, filas, productosATransferir, onDestino, onFilas }: DevolverElRemanenteProps) {
  const resumen = useResumenDeJornada(jornadaId)
  const catalogo = useProductosParaRendicion()
  const saldos = useSaldosCompletos(ubicacionId)
  const ubicaciones = useUbicaciones(true)

  const nombres = new Map(catalogo.productos.map((p) => [p.id, p.nombre]))
  const nombreDe = (productoId: string) => nombres.get(productoId) ?? `Producto ${productoId.slice(0, 8)}`
  const referencias = new Map<string, ReferenciaDePresentacion>()
  for (const saldo of saldos.lineas) {
    const referencia = referenciaDeRespuesta(saldo.unidades_referencia, saldo.nombre_referencia)
    if (referencia !== null) referencias.set(saldo.producto_id, referencia)
  }
  const depositos = (ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter(
    (u) => u.activo && u.tipo === 'DEPOSITO',
  )

  // La precarga necesita los tres: sin ellos quedaría congelada en vacío (sin precargar ≠ precargado vacío).
  const hayError = resumen.isError || catalogo.error !== null || saldos.error !== null
  const listo = resumen.isSuccess && !catalogo.cargando && saldos.completo

  const elegir = (id: string) => {
    if (!listo) return
    const elegido = depositos.find((d) => d.id === id)
    if (elegido === undefined) {
      onDestino({ id: '', nombre: '' }, null)
      return
    }
    // D6: todo lo contado; una jornada sin conteo usa el stock actual del vehículo.
    const contados =
      resumen.data?.con_conteo === true
        ? resumen.data.lineas.map((l) => ({ productoId: l.producto_id, contado: l.contado ?? 0 }))
        : saldos.lineas.map((s) => ({ productoId: s.producto_id, contado: s.cantidad_base }))
    onDestino({ id: elegido.id, nombre: elegido.nombre }, filas === null ? precargarDevolucion(contados, referencias) : null)
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <label htmlFor="cierre-destino" className="text-sm font-medium text-primary">
          Devolver el remanente a
        </label>
        <Ayuda clave="stock.remanente" />
      </div>
      <select
        id="cierre-destino"
        className={CLASE_CONTROL}
        value={destino.id}
        disabled={!listo}
        onChange={(evento) => elegir(evento.target.value)}
      >
        <option value="">No devolver el remanente</option>
        {depositos.map((deposito) => (
          <option key={deposito.id} value={deposito.id}>
            {deposito.nombre}
          </option>
        ))}
      </select>
      {!listo && !hayError && <p className="text-sm text-primary/70">Cargando el remanente…</p>}
      {!listo && hayError && <Alert>No pudimos leer el remanente para precargar la devolución. Cerrá y volvé a abrir el diálogo.</Alert>}

      {destino.id !== '' && filas !== null && (
        <>
          <table className="w-full border-collapse text-left text-sm" aria-label="Remanente a devolver">
            <thead>
              <tr className="border-b border-border">
                <th className="py-1 pr-3 font-medium">Producto</th>
                <th className="py-1 font-medium">Cantidad a devolver</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((fila, indice) => (
                <tr key={fila.productoId} className="border-b border-border/50">
                  <td className="py-1 pr-3">{nombreDe(fila.productoId)}</td>
                  <td className="py-1">
                    <CampoDeCantidad
                      producto={nombreDe(fila.productoId)}
                      valor={{ cajas: fila.cajas, unidades: fila.unidades }}
                      referencia={referencias.get(fila.productoId) ?? null}
                      onChange={(valor) => onFilas((actual) => (actual ?? []).map((f, i) => (i === indice ? { ...f, ...valor } : f)))}
                    />
                    <TotalDeFila fila={fila} referencia={referencias.get(fila.productoId) ?? null} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-sm text-primary">{textoDeDevolucion(productosATransferir, destino.nombre)}</p>
        </>
      )}
    </div>
  )
}

/** El total de la fila en unidad base (con su equivalencia en la presentación de referencia, CAT-08). */
function TotalDeFila({ fila, referencia }: { fila: FilaDeDevolucion; referencia: ReferenciaDePresentacion | null }) {
  const total = totalDeDevolucion(fila)
  if (total === null) return null
  return <p className="mt-1 text-xs text-primary/70">Total: {formatearCantidad(total, referencia)}</p>
}
