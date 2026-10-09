import { useState } from 'react'
import { useFieldArray, useForm, useWatch, type Control, type UseFormRegister } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { referenciaDeRespuesta } from '../../../domain/stock/cantidades'
import {
  armarTransferencia,
  cantidadDeLinea,
  previsualizarTransferencia,
  type LineaDeEntrada,
} from '../../../domain/stock/operaciones'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { LineaDeStock, Ubicacion } from '../../../features/stock/api'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../features/stock/errores'
import { useRegistrarTransferencia, useSaldosCompletos, useUbicaciones } from '../../../features/stock/hooks'
import {
  AVISO_REQUIERE_CONEXION,
  CLASE_CONTROL,
  CLASE_ENLACE,
  PantallaSinPermiso,
  SaldoResultante,
} from './piezasDeOperacion'

const TITULO = 'Nueva transferencia'

interface LineaDeFormulario {
  productoId: string
  cajas: string
  unidades: string
}

interface DatosDelFormulario {
  origenId: string
  destinoId: string
  observacion: string
  lineas: LineaDeFormulario[]
}

const LINEA_VACIA: LineaDeFormulario = { productoId: '', cajas: '', unidades: '' }

interface ErrorDeEnvio {
  mensaje: string
  indice?: number
}

/**
 * Alta de una transferencia entre ubicaciones (change 14, tarea 13.1; spec
 * `administracion-de-stock`; STK-07, TR-07, `design.md` D7, D11). Ruta
 * `/admin/stock/transferencias/nueva`, con `?origen=` desde "Transferir desde acá". Los productos
 * se eligen **solo** del stock del origen (D7), con cajas + unidades; cada línea muestra el saldo
 * actual y el resultante en origen y destino y marca un resultado negativo. El `operation_id` es
 * nuevo por contenido y se reutiliza en el reintento. Es `ONLINE` puro: no se encola nada.
 */
export function TransferenciaFormScreen() {
  return (
    <SiTienePermiso
      permiso="TRANSFERIR_STOCK"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para registrar transferencias." />}
    >
      <CargaDeUbicaciones />
    </SiTienePermiso>
  )
}

/** Espera las ubicaciones antes de montar el formulario: el origen precargado necesita su opción. */
function CargaDeUbicaciones() {
  const ubicaciones = useUbicaciones(true)
  if (ubicaciones.isPending) return <p>Cargando…</p>
  if (ubicaciones.isError) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>No se pudieron obtener las ubicaciones.</Alert>
      </main>
    )
  }
  return <Formulario ubicaciones={ubicaciones.data.pages.flatMap((pagina) => pagina.items)} />
}

function lineasDeEntrada(
  lineas: readonly (Partial<LineaDeFormulario> | undefined)[] | undefined,
  saldosDelOrigen: readonly LineaDeStock[],
): LineaDeEntrada[] {
  return (lineas ?? []).map((cruda) => {
    const productoId = cruda?.productoId ?? ''
    const delOrigen = saldosDelOrigen.find((saldo) => saldo.producto_id === productoId)
    return {
      productoId,
      cajas: cruda?.cajas ?? '',
      unidades: cruda?.unidades ?? '',
      negativa: false,
      unidadesPorCaja: delOrigen?.unidades_referencia ?? null,
      nombrePresentacion: delOrigen?.nombre_referencia ?? null,
    }
  })
}

function Formulario({ ubicaciones }: { ubicaciones: Ubicacion[] }) {
  const navigate = useNavigate()
  const [parametros] = useSearchParams()
  const registrar = useRegistrarTransferencia()
  const [error, setError] = useState<ErrorDeEnvio | null>(null)
  const [enviando, setEnviando] = useState(false)

  const origenInicial = parametros.get('origen') ?? ''
  const { register, handleSubmit, control } = useForm<DatosDelFormulario>({
    defaultValues: {
      origenId: ubicaciones.some((u) => u.id === origenInicial) ? origenInicial : '',
      destinoId: '',
      observacion: '',
      lineas: [{ ...LINEA_VACIA }],
    },
  })
  const { fields, append, remove, replace } = useFieldArray({ control, name: 'lineas' })
  const valores = useWatch({ control })
  const origenId = valores.origenId ?? ''
  const destinoId = valores.destinoId ?? ''
  const saldosOrigen = useSaldosCompletos(origenId === '' ? undefined : origenId)
  const saldosDestino = useSaldosCompletos(destinoId === '' ? undefined : destinoId)
  const nombreDe = (id: string) => ubicaciones.find((u) => u.id === id)?.nombre ?? ''

  const armado = armarTransferencia({
    origenId,
    destinoId,
    observacion: valores.observacion ?? '',
    lineas: lineasDeEntrada(valores.lineas, saldosOrigen.lineas),
  })
  // El `operation_id` cambia cuando cambia el contenido y se conserva si se reintenta lo mismo.
  const operationId = useOperationIdPorContenido(armado.ok ? armado.cuerpo : null)

  async function enviar() {
    if (!armado.ok) {
      setError({ mensaje: armado.mensaje, indice: armado.indice })
      return
    }
    setError(null)
    setEnviando(true)
    try {
      const resultado = await registrar.mutateAsync({ ...armado.cuerpo, operationId })
      navigate(`/admin/stock/transferencias/${resultado.id}`)
    } catch (falla) {
      setError({
        mensaje: mensajeDeErrorDeStock(falla, 'transferencia'),
        indice: falla instanceof ErrorDeStock ? falla.linea : undefined,
      })
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <Link to="/admin/stock/transferencias" className={CLASE_ENLACE}>
            Volver al listado
          </Link>
        }
      />
      <Card>
        <form onSubmit={(evento) => void handleSubmit(enviar)(evento)} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-primary">
              Origen
              <select
                className={CLASE_CONTROL}
                {...register('origenId', { onChange: () => replace([{ ...LINEA_VACIA }]) })}
              >
                <option value="">Elegí el origen</option>
                {ubicaciones.map((ubicacion) => (
                  <option key={ubicacion.id} value={ubicacion.id}>
                    {ubicacion.nombre}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-primary">
              Destino
              <select className={CLASE_CONTROL} {...register('destinoId')}>
                <option value="">Elegí el destino</option>
                {ubicaciones.map((ubicacion) => (
                  <option key={ubicacion.id} value={ubicacion.id}>
                    {ubicacion.nombre}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {fields.map((campo, indice) => (
            <LineaEditor
              key={campo.id}
              indice={indice}
              register={register}
              control={control}
              saldosOrigen={saldosOrigen.lineas}
              saldosDestino={saldosDestino.lineas}
              nombreOrigen={nombreDe(origenId)}
              nombreDestino={nombreDe(destinoId)}
              error={error?.indice === indice ? error.mensaje : null}
              puedeQuitar={fields.length > 1}
              onQuitar={() => remove(indice)}
            />
          ))}

          <div>
            <Boton type="button" variante="secundario" onClick={() => append({ ...LINEA_VACIA })}>
              Agregar línea
            </Boton>
          </div>

          <label className="flex flex-col gap-1 text-sm text-primary">
            Observación
            <textarea className={CLASE_CONTROL} rows={2} {...register('observacion')} />
          </label>

          {error && error.indice === undefined && <Alert>{error.mensaje}</Alert>}

          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={enviando || registrar.isPending}>
              Registrar transferencia
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

interface LineaEditorProps {
  indice: number
  register: UseFormRegister<DatosDelFormulario>
  control: Control<DatosDelFormulario>
  saldosOrigen: readonly LineaDeStock[]
  saldosDestino: readonly LineaDeStock[]
  nombreOrigen: string
  nombreDestino: string
  error: string | null
  puedeQuitar: boolean
  onQuitar: () => void
}

function LineaEditor({
  indice,
  register,
  control,
  saldosOrigen,
  saldosDestino,
  nombreOrigen,
  nombreDestino,
  error,
  puedeQuitar,
  onQuitar,
}: LineaEditorProps) {
  const linea = useWatch({ control, name: `lineas.${String(indice)}` as `lineas.${number}` })
  // D7: solo los productos que figuran en el origen con stock.
  const opciones = saldosOrigen.filter((saldo) => saldo.cantidad_base > 0)
  const delOrigen = saldosOrigen.find((saldo) => saldo.producto_id === linea.productoId)
  const delDestino = saldosDestino.find((saldo) => saldo.producto_id === linea.productoId)
  const referencia = delOrigen ? referenciaDeRespuesta(delOrigen.unidades_referencia, delOrigen.nombre_referencia) : null
  const sinReferencia = delOrigen !== undefined && referencia === null

  const cantidad = delOrigen
    ? cantidadDeLinea({
        productoId: linea.productoId,
        cajas: linea.cajas ?? '',
        unidades: linea.unidades ?? '',
        negativa: false,
        unidadesPorCaja: referencia?.unidades ?? null,
        nombrePresentacion: referencia?.nombre ?? null,
      })
    : null
  const saldos =
    delOrigen && cantidad?.ok && cantidad.cantidadBase > 0
      ? previsualizarTransferencia(delOrigen.cantidad_base, delDestino?.cantidad_base ?? 0, cantidad.cantidadBase)
      : null

  const nombre = (campo: keyof LineaDeFormulario) => `lineas.${String(indice)}.${campo}` as `lineas.${number}.${typeof campo}`

  return (
    <fieldset className="flex flex-col gap-3 rounded-md border border-border p-3">
      <legend className="px-1 text-sm font-medium text-primary">Línea {indice + 1}</legend>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-primary">
          Producto
          <select className={CLASE_CONTROL} {...register(nombre('productoId'))}>
            <option value="">Elegí un producto</option>
            {opciones.map((saldo) => (
              <option key={saldo.producto_id} value={saldo.producto_id}>
                {saldo.producto_codigo} · {saldo.producto_nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-primary">
          {referencia?.nombre ?? 'Cajas'}
          <input
            inputMode="numeric"
            autoComplete="off"
            disabled={sinReferencia}
            className={CLASE_CONTROL}
            {...register(nombre('cajas'))}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-primary">
          Unidades
          <input inputMode="numeric" autoComplete="off" className={CLASE_CONTROL} {...register(nombre('unidades'))} />
        </label>
        {puedeQuitar && (
          <Boton type="button" variante="secundario" onClick={onQuitar}>
            Quitar línea
          </Boton>
        )}
      </div>

      {referencia !== null && (
        <p className="text-xs text-primary/70">
          Una {referencia.nombre ?? 'caja'} tiene {referencia.unidades} unidades.
        </p>
      )}
      {saldos !== null && (
        <div className="flex flex-wrap gap-6">
          <SaldoResultante ubicacion={nombreOrigen} saldo={saldos.origen} referencia={referencia} />
          <SaldoResultante ubicacion={nombreDestino} saldo={saldos.destino} referencia={referencia} />
        </div>
      )}
      {error && <Alert>{error}</Alert>}
    </fieldset>
  )
}

export default TransferenciaFormScreen
