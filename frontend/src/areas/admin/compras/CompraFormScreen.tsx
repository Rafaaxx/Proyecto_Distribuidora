import { useState } from 'react'
import { useFieldArray, useForm, useWatch, type Control, type UseFormRegister } from 'react-hook-form'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  calcularFaltanteDeMedios,
  calcularVistaPrevia,
  construirSolicitudDeCompra,
  contextoDeLinea,
  presentacionesDeCompra,
  puedeConfirmar,
  type FormularioDeCompra,
  type LineaDeFormulario,
  type MedioDeFormulario,
  type VistaPreviaDeLinea,
} from '../../../domain/compras/formularioCompra'
import { avisoDeSaldoAFavorEnCompra } from '../../../domain/compras/saldoAFavor'
import { formatearCosto, formatearImporte } from '../../../lib/money'
import { formatearCantidad, referenciaDePresentaciones, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import type { CompraConfirmarResultado, MedioPago } from '../../../features/compras/api'
import { ErrorDeCompras, PermisoRequeridoComprasError } from '../../../features/compras/errores'
import { useConfirmarCompra, useMediosPago } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { useDetallesDeProductos, useProductosDelProveedor } from '../../../features/catalogo/useListados'
import { useAlicuotas } from '../../../features/configuracion/useAlicuotas'
import { useConfiguracionFiscal } from '../../../features/configuracion/useConfiguracionFiscal'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { useSaldoDelProveedor } from '../../../features/pagos-proveedores/hooks'
import { useOpcionesDeProveedores } from '../../../features/proveedores/useListados'
import { useUbicaciones } from '../../../features/stock/hooks'
import { CompraResultado } from './CompraResultado'

/**
 * Alta de compra (change 11, tarea 12.1; spec `administracion-de-compras`). Solo con
 * `REGISTRAR_COMPRA` (D14). Toda la cuenta (vista previa por línea, totales, faltante de
 * medios, cuerpo del comando) vive en `domain/compras/formularioCompra.ts`; este
 * componente solo la pinta. El `Operation-Id` se conserva mientras el contenido no cambia
 * (INV-06).
 *
 * 11b (CST-06): la regla de IVA sale de `GET /configuracion/fiscal`. Sin crédito fiscal
 * (monotributo, exento) el valor de la línea es el pagado: no hay casilla "Incluye IVA" ni
 * "IVA sugerido" y el IVA es costo. Mientras la condición no se conoce no se calcula ni se
 * confirma.
 */

const SIN_PERMISO = 'No tenés permiso para registrar compras.'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

const LINEA_VACIA: LineaDeFormulario = {
  productoId: '',
  presentacionId: '',
  cantidad: '',
  valor: '',
  incluyeIva: false,
  bonificacionPorcentaje: '0',
}
const MEDIO_VACIO: MedioDeFormulario = { medioPagoId: '', importe: '', referencia: '' }

function fechaDeHoy(): string {
  const ahora = new Date()
  const mes = String(ahora.getMonth() + 1).padStart(2, '0')
  const dia = String(ahora.getDate()).padStart(2, '0')
  return `${String(ahora.getFullYear())}-${mes}-${dia}`
}

function valoresIniciales(): FormularioDeCompra {
  return {
    proveedorId: '',
    fecha: fechaDeHoy(),
    ubicacionId: '',
    condicion: 'CREDITO',
    numeroComprobante: '',
    observacion: '',
    lineas: [LINEA_VACIA],
    medios: [],
  }
}

export function CompraFormScreen() {
  return (
    <SiTienePermiso
      permiso="REGISTRAR_COMPRA"
      fallback={
        <main className="flex flex-col gap-4">
          <PageHeader titulo="Nueva compra" />
          <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
        </main>
      }
    >
      <CompraFormulario />
    </SiTienePermiso>
  )
}

interface CompraEnviada {
  resultado: CompraConfirmarResultado
  computaCreditoFiscal: boolean
  formulario: FormularioDeCompra
  nombresDeProductos: Record<string, string>
}

function CompraFormulario() {
  const { register, control, setValue, getValues } = useForm<FormularioDeCompra>({ defaultValues: valoresIniciales() })
  const lineasField = useFieldArray({ control, name: 'lineas' })
  const mediosField = useFieldArray({ control, name: 'medios' })
  const formulario = useWatch({ control }) as FormularioDeCompra
  const lineas = formulario.lineas
  const medios = formulario.medios

  const [totalManual, setTotalManual] = useState<string | null>(null)
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [erroresDeLinea, setErroresDeLinea] = useState<Record<number, string>>({})
  const [enviada, setEnviada] = useState<CompraEnviada | null>(null)

  const proveedores = useOpcionesDeProveedores()
  const ubicaciones = useUbicaciones(true)
  const { productos } = useProductosDelProveedor(formulario.proveedorId === '' ? undefined : formulario.proveedorId)
  const detalles = useDetallesDeProductos(lineas.map((linea) => linea.productoId))
  const alicuotas = useAlicuotas()
  const mediosPago = useMediosPago()
  const confirmar = useConfirmarCompra()
  const fiscal = useConfiguracionFiscal()
  // Aviso informativo (change 12, PAG-02): si la lectura falla no hay aviso y la compra se carga igual.
  const saldoDelProveedor = useSaldoDelProveedor(formulario.proveedorId === '' ? undefined : formulario.proveedorId)
  const avisoDeSaldoAFavor = avisoDeSaldoAFavorEnCompra(saldoDelProveedor.data)
  const computaCreditoFiscal = fiscal.data?.computa_credito_fiscal ?? null

  const listaDeAlicuotas = alicuotas.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const contextos = lineas.map((linea, indice) => contextoDeLinea(detalles[indice]?.data, linea.presentacionId, listaDeAlicuotas))
  const vistaPrevia = calcularVistaPrevia(lineas, contextos, computaCreditoFiscal)
  const totalSugerido = vistaPrevia.totales?.totalFacturaSugerido.toFixed(2) ?? ''
  const totalFactura = totalManual ?? totalSugerido
  const medioDePago = (id: string): MedioPago | undefined => mediosPago.data?.items.find((m) => m.id === id)
  const mediosRequierenReferencia = new Set((mediosPago.data?.items ?? []).filter((m) => m.requiere_referencia).map((m) => m.id))
  const habilitado = puedeConfirmar({ formulario, vistaPrevia, totalFactura, mediosRequierenReferencia })
  const faltante = calcularFaltanteDeMedios(totalFactura, medios)
  const operationId = useOperationIdPorContenido({ formulario, totalFactura })

  const alEnviar = async (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    if (!habilitado || computaCreditoFiscal === null) return
    setErrorGeneral(null)
    setErroresDeLinea({})
    const enviado = getValues()
    try {
      const resultado = await confirmar.mutateAsync({ ...construirSolicitudDeCompra(enviado, totalFactura, computaCreditoFiscal), operationId })
      setEnviada({
        resultado,
        computaCreditoFiscal,
        formulario: enviado,
        nombresDeProductos: Object.fromEntries(productos.map((p) => [p.id, p.nombre])),
      })
    } catch (error) {
      if (error instanceof PermisoRequeridoComprasError) {
        setErrorGeneral(SIN_PERMISO)
      } else if (error instanceof ErrorDeCompras && error.linea !== null) {
        setErroresDeLinea({ [error.linea]: error.message })
      } else if (error instanceof ErrorDeCompras) {
        setErrorGeneral(error.message)
      } else {
        setErrorGeneral('No se pudo enviar la compra. Podés reintentar: se reenvía la misma operación.')
      }
    }
  }

  if (enviada) {
    return (
      <CompraResultado
        resultado={enviada.resultado}
        computaCreditoFiscal={enviada.computaCreditoFiscal}
        formulario={enviada.formulario}
        nombresDeProductos={enviada.nombresDeProductos}
      />
    )
  }

  const cambiarProveedor = () => {
    // Los productos dependen del proveedor: se descartan las líneas cargadas.
    setValue('lineas', [LINEA_VACIA])
    setTotalManual(null)
    setErroresDeLinea({})
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Nueva compra" />
      <form onSubmit={(e) => void alEnviar(e)} noValidate className="flex flex-col gap-4">
        {errorGeneral && <Alert>{errorGeneral}</Alert>}
        {fiscal.isError && <Alert>No se pudo leer la condición frente al IVA de la organización. Recargá la pantalla.</Alert>}

        <Card className="flex flex-wrap items-end gap-3">
          <Campo id="compra-proveedor" etiqueta="Proveedor">
            <select
              id="compra-proveedor"
              className={CLASE_CONTROL}
              {...register('proveedorId', { onChange: cambiarProveedor })}
            >
              <option value="">Elegí un proveedor</option>
              {(proveedores.data?.pages.flatMap((pagina) => pagina.items) ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="compra-fecha" etiqueta="Fecha">
            <input id="compra-fecha" type="date" className={CLASE_CONTROL} {...register('fecha')} />
          </Campo>
          <Campo id="compra-ubicacion" etiqueta="Ubicación de destino">
            <select id="compra-ubicacion" className={CLASE_CONTROL} {...register('ubicacionId')}>
              <option value="">Elegí una ubicación</option>
              {(ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="compra-condicion" etiqueta="Condición">
            <select id="compra-condicion" className={CLASE_CONTROL} {...register('condicion')}>
              <option value="CREDITO">A crédito</option>
              <option value="CONTADO">De contado</option>
            </select>
          </Campo>
          <Campo id="compra-comprobante" etiqueta="Número de comprobante (opcional)">
            <input id="compra-comprobante" className={CLASE_CONTROL} {...register('numeroComprobante')} />
          </Campo>
          <Campo id="compra-observacion" etiqueta="Observación (opcional)">
            <input id="compra-observacion" className={CLASE_CONTROL} {...register('observacion')} />
          </Campo>
        </Card>

        {avisoDeSaldoAFavor && (
          <p role="status" className="rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-primary">
            {avisoDeSaldoAFavor}
          </p>
        )}

        {lineasField.fields.map((campo, indice) => (
          <LineaDeCompra
            key={campo.id}
            indice={indice}
            register={register}
            control={control}
            productos={productos}
            presentaciones={presentacionesDeCompra(detalles[indice]?.data?.presentaciones)}
            referencia={referenciaDePresentaciones(detalles[indice]?.data?.presentaciones)}
            vista={vistaPrevia.lineas[indice] ?? { estado: 'incompleta' }}
            computaCreditoFiscal={computaCreditoFiscal}
            errorDelServidor={erroresDeLinea[indice]}
            alCambiarProducto={() => setValue(`lineas.${indice}.presentacionId`, '')}
            onQuitar={lineasField.fields.length > 1 ? () => lineasField.remove(indice) : undefined}
          />
        ))}
        <Boton variante="secundario" className="self-start" onClick={() => lineasField.append(LINEA_VACIA)}>
          Agregar línea
        </Boton>

        <Card className="flex flex-col gap-2 text-sm text-primary">
          <p>
            {computaCreditoFiscal === false ? 'Total' : 'Total neto'}:{' '}
            <span data-testid="total-neto">{vistaPrevia.totales ? formatearImporte(vistaPrevia.totales.totalNeto) : '—'}</span>
          </p>
          {computaCreditoFiscal === true && (
            <p>
              IVA sugerido:{' '}
              <span data-testid="iva-sugerido">{vistaPrevia.totales ? formatearImporte(vistaPrevia.totales.ivaSugerido) : '—'}</span>
            </p>
          )}
          <Campo id="compra-total-factura" etiqueta="Total de factura">
            <input
              id="compra-total-factura"
              className={`${CLASE_CONTROL} w-40`}
              value={totalFactura}
              onChange={(evento) => setTotalManual(evento.target.value)}
              inputMode="decimal"
            />
          </Campo>
          {totalManual !== null && (
            <button type="button" className="self-start text-xs text-primary/70 hover:underline" onClick={() => setTotalManual(null)}>
              Volver al total sugerido
            </button>
          )}
        </Card>

        {formulario.condicion === 'CONTADO' && (
          <Card className="flex flex-col gap-3">
            <h2 className="text-base font-semibold text-primary">Medios de pago</h2>
            {mediosField.fields.map((campo, indice) => (
              <div key={campo.id} className="flex flex-wrap items-end gap-3">
                <Campo id={`medios.${indice}.medioPagoId`} etiqueta="Medio de pago">
                  <select id={`medios.${indice}.medioPagoId`} className={CLASE_CONTROL} {...register(`medios.${indice}.medioPagoId` as const)}>
                    <option value="">Elegí un medio</option>
                    {(mediosPago.data?.items ?? []).map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.nombre}
                      </option>
                    ))}
                  </select>
                </Campo>
                <Campo id={`medios.${indice}.importe`} etiqueta="Importe del medio">
                  <input id={`medios.${indice}.importe`} className={`${CLASE_CONTROL} w-32`} {...register(`medios.${indice}.importe` as const)} />
                </Campo>
                {medioDePago(medios[indice]?.medioPagoId ?? '')?.requiere_referencia && (
                  <Campo id={`medios.${indice}.referencia`} etiqueta="Referencia">
                    <input id={`medios.${indice}.referencia`} className={CLASE_CONTROL} {...register(`medios.${indice}.referencia` as const)} />
                  </Campo>
                )}
                <Boton variante="peligro" onClick={() => mediosField.remove(indice)}>
                  Quitar medio
                </Boton>
              </div>
            ))}
            <Boton variante="secundario" className="self-start" onClick={() => mediosField.append(MEDIO_VACIO)}>
              Agregar medio
            </Boton>
            <p className="text-sm text-primary" data-testid="faltante-medios">
              {faltante.isZero()
                ? 'Los medios suman el total.'
                : faltante.gt(0)
                  ? `Faltan ${formatearImporte(faltante)}`
                  : `Sobran ${formatearImporte(faltante.neg())}`}
            </p>
          </Card>
        )}

        <div className="flex gap-2">
          <Boton type="submit" disabled={!habilitado || confirmar.isPending}>
            Confirmar compra
          </Boton>
          <Link to="/admin/compras" className="self-center text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>
    </main>
  )
}

interface LineaProps {
  indice: number
  register: UseFormRegister<FormularioDeCompra>
  control: Control<FormularioDeCompra>
  productos: { id: string; nombre: string }[]
  presentaciones: { id: string; nombre: string }[]
  referencia: ReferenciaDePresentacion | null
  vista: VistaPreviaDeLinea
  /** CST-06; `null` mientras no se conoce. */
  computaCreditoFiscal: boolean | null
  errorDelServidor: string | undefined
  alCambiarProducto: () => void
  onQuitar?: () => void
}

function LineaDeCompra({
  indice,
  register,
  productos,
  presentaciones,
  referencia,
  vista,
  computaCreditoFiscal,
  errorDelServidor,
  alCambiarProducto,
  onQuitar,
}: LineaProps) {
  const base = `lineas.${indice}` as const
  return (
    <Card className="flex flex-col gap-2" data-testid={`linea-${indice}`}>
      <div className="flex flex-wrap items-end gap-3">
        <Campo id={`${base}.productoId`} etiqueta="Producto">
          <select
            id={`${base}.productoId`}
            className={CLASE_CONTROL}
            {...register(`${base}.productoId`, { onChange: alCambiarProducto })}
          >
            <option value="">Elegí un producto</option>
            {productos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id={`${base}.presentacionId`} etiqueta="Presentación">
          <select id={`${base}.presentacionId`} className={CLASE_CONTROL} {...register(`${base}.presentacionId`)}>
            <option value="">Elegí una presentación</option>
            {presentaciones.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id={`${base}.cantidad`} etiqueta="Cantidad">
          <input id={`${base}.cantidad`} className={`${CLASE_CONTROL} w-24`} {...register(`${base}.cantidad`)} />
        </Campo>
        <Campo id={`${base}.valor`} etiqueta={computaCreditoFiscal === false ? 'Valor pagado' : 'Valor'}>
          <input id={`${base}.valor`} className={`${CLASE_CONTROL} w-28`} {...register(`${base}.valor`)} />
        </Campo>
        {computaCreditoFiscal === true && (
          <label className="flex items-center gap-1 text-sm text-primary">
            <input type="checkbox" {...register(`${base}.incluyeIva`)} />
            Incluye IVA
          </label>
        )}
        <Campo id={`${base}.bonificacionPorcentaje`} etiqueta="Bonificación %">
          <input id={`${base}.bonificacionPorcentaje`} className={`${CLASE_CONTROL} w-20`} {...register(`${base}.bonificacionPorcentaje`)} />
        </Campo>
        {onQuitar && (
          <Boton variante="peligro" onClick={onQuitar}>
            Quitar línea
          </Boton>
        )}
      </div>
      <div className="text-sm text-primary/70" data-testid={`linea-${indice}-vista-previa`}>
        {vista.estado === 'lista' && (
          <>
            Cantidad base: {formatearCantidad(vista.calculada.cantidadBase, referencia)} · Costo base:{' '}
            {formatearCosto(vista.calculada.costoBase)} · Importe neto: {formatearImporte(vista.calculada.importeNeto)}
          </>
        )}
        {vista.estado === 'error' && <span className="text-danger">{vista.mensaje}</span>}
      </div>
      {errorDelServidor && <Alert>{errorDelServidor}</Alert>}
    </Card>
  )
}

export default CompraFormScreen
