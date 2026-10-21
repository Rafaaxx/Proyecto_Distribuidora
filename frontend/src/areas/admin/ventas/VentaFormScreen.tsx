import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useFieldArray, useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { formatearMonto, textoDeSaldo } from '../../../domain/cuentas-corrientes/presentacion'
import {
  AVISO_CONSUMIDOR_FINAL_DE_CONTADO,
  FALTA_CONTADO_DE_CONSUMIDOR_FINAL,
  decidirConfirmacionDeVenta,
  evaluarContadoDeConsumidorFinal,
  sumarCobranzaDeVenta,
  textoDeSaldoResultanteDeVenta,
  type LecturaDeSaldoDeCliente,
} from '../../../domain/ventas/calculoDeVenta'
import { admiteCajas, admiteUnidadesSueltas, cantidadInicialDeProducto } from '../../../domain/ventas/composicion'
import {
  aplicarValoresDelServidor,
  construirSolicitudDeVenta,
  diferenciasConElServidor,
  puedeConfirmarVenta,
  type FormularioDeVenta,
  type ValoresDelServidor,
} from '../../../domain/ventas/formularioVenta'
import {
  almacenDelNavegador,
  correlativoDeNumero,
  guardarCorrelativo,
  leerCorrelativoGuardado,
  proponerNumero,
  proponerTrasDuplicado,
} from '../../../domain/ventas/numeracion'
import {
  aProductoConPrecio,
  armarPedido,
  type ItemDelPedido,
  type ProductoConPrecio,
} from '../../../domain/ventas/pedido'
import { AMBITO_DE_LISTA_ANTERIOR, etiquetaDeVersion } from '../../../domain/ventas/presentacion'
import { useOpcionesDeClientes, useSaldoDelCliente } from '../../../features/cobranzas/hooks'
import { useMediosPago, useMotivos } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { useOpcionesDeListas } from '../../../features/precios/hooks'
import { useJornadaActual, useUbicaciones } from '../../../features/stock/hooks'
import type { ProductoParaVender, VentaConfirmarResultado } from '../../../features/ventas/api'
import { clavesVentas, type ContextoDePrecios } from '../../../features/ventas/claves'
import {
  campoDelError,
  ErrorDeVentas,
  PermisoRequeridoVentasError,
  productosSinPrecioDe,
  valoresDelServidorDe,
  type CampoDeVenta,
} from '../../../features/ventas/errores'
import {
  useBuscarPrecios,
  useConfirmarVenta,
  useNumeracion,
  usePreciosDeProductos,
  useVersionesElegibles,
} from '../../../features/ventas/hooks'
import { useTextoConDemora } from '../../../features/ventas/useTextoConDemora'
import { generarOperationId } from '../../../lib/api/operationId'
import { parsearImporteDesdeApi } from '../../../lib/money'
import { MediosDeCobranza } from '../cobranzas/MediosDeCobranza'
import { BuscadorDeProductos } from './BuscadorDeProductos'
import { ItemDeVenta } from './ItemDeVenta'
import { SIN_PERMISO_PARA_VENDER, VentasSinPermiso } from './VentasSinPermiso'

/**
 * Alta de venta con conexión desde `/admin` (change 18a, tarea 12.2; spec
 * `administracion-de-ventas`; `design.md` D2, D3, D4, D6, D8, D12, D21). Solo con `VENDER`. Toda la
 * cuenta (composición cajas + unidades, brutos, total, saldo resultante, esquema, cuerpo del
 * comando, número propuesto) vive en `domain/ventas/`; este componente solo la pinta. El
 * `Operation-Id` se conserva mientras el contenido no cambia (INV-06) y los identificadores de la
 * venta, de la cobranza y de cada línea, mientras no se registra otra venta: un reintento nunca
 * duplica. Las ayudas "(?)" son de la tarea 13.1.
 */

const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MEDIO_VACIO = { medioPagoId: '', importe: '', referencia: '' }
const VALORES_INICIALES: FormularioDeVenta = {
  clienteId: '',
  ubicacionId: '',
  numero: '',
  listaId: '',
  versionId: '',
  motivoId: '',
  observacionCobranza: '',
  medios: [],
}
const MENSAJE_DE_RED =
  'No se pudo enviar la venta. Revisá la conexión y reintentá: se reenvía la misma operación.'

interface ItemEnPantalla extends ItemDelPedido {
  nombre: string
  /** Identificador de línea por presentación, generado al agregar y estable en los reintentos. */
  idsDeLinea: Record<string, string>
}

interface ValoresAceptados {
  clave: string
  valores: ValoresDelServidor
  operationId: string
}

interface PrecioDifiere {
  valores: ValoresDelServidor
  totalAnterior: string
}

type ErroresDeCampo = Partial<Record<CampoDeVenta, string>>

export function VentaFormScreen() {
  return (
    <SiTienePermiso
      permiso="VENDER"
      fallback={<VentasSinPermiso titulo="Nueva venta" mensaje={SIN_PERMISO_PARA_VENDER} />}
    >
      <VentaFormulario />
    </SiTienePermiso>
  )
}

function VentaFormulario() {
  const { tiene } = usePermisos()
  const queryClient = useQueryClient()
  const puedeElegirLista = tiene('USAR_LISTA_ANTERIOR')
  const { register, control, setValue, reset } = useForm<FormularioDeVenta>({ defaultValues: VALORES_INICIALES })
  const mediosField = useFieldArray({ control, name: 'medios' })
  const formulario = useWatch({ control }) as FormularioDeVenta
  const medios = formulario.medios ?? []

  const [ventaId, setVentaId] = useState(generarOperationId)
  const [cobranzaId, setCobranzaId] = useState(generarOperationId)
  const [busquedaCliente, setBusquedaCliente] = useState('')
  const [textoProducto, setTextoProducto] = useState('')
  const [items, setItems] = useState<ItemEnPantalla[]>([])
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [erroresDeCampo, setErroresDeCampo] = useState<ErroresDeCampo>({})
  const [erroresDeMedio, setErroresDeMedio] = useState<Record<number, string>>({})
  const [confirmando, setConfirmando] = useState(false)
  const [precioDifiere, setPrecioDifiere] = useState<PrecioDifiere | null>(null)
  const [aceptados, setAceptados] = useState<ValoresAceptados | null>(null)
  const [registrada, setRegistrada] = useState<VentaConfirmarResultado | null>(null)
  const ubicacionAutoElegida = useRef(false)

  const textoDemorado = useTextoConDemora(textoProducto)
  const clientes = useOpcionesDeClientes(busquedaCliente, true)
  const mediosPago = useMediosPago()
  const motivos = useMotivos(AMBITO_DE_LISTA_ANTERIOR)
  const listas = useOpcionesDeListas(puedeElegirLista)
  const numeracion = useNumeracion()
  const ubicacionesQuery = useUbicaciones(true)
  const jornada = useJornadaActual(tiene('ABRIR_JORNADA'))
  const confirmar = useConfirmarVenta()

  // --- ubicación o jornada (D3) -------------------------------------------------------------
  const esperandoJornada = tiene('ABRIR_JORNADA') && jornada.isPending
  const jornadaAbierta = jornada.data?.estado === 'ABIERTA' ? jornada.data : null
  const ubicaciones = useMemo(() => ubicacionesQuery.data?.pages.flatMap((pagina) => pagina.items) ?? [], [ubicacionesQuery.data])
  const ubicacionDeLaVenta = jornadaAbierta?.ubicacion_id ?? (formulario.ubicacionId === '' ? undefined : formulario.ubicacionId)

  useEffect(() => {
    if (ubicacionAutoElegida.current || esperandoJornada || jornadaAbierta !== null) return
    const unica = ubicaciones.length === 1 ? ubicaciones[0] : undefined
    if (unica === undefined) return
    ubicacionAutoElegida.current = true
    setValue('ubicacionId', unica.id)
  }, [ubicaciones, esperandoJornada, jornadaAbierta, setValue])

  // --- número propuesto (D4) ----------------------------------------------------------------
  const prefijo = numeracion.data?.prefijo
  const ultimoCorrelativo = numeracion.data?.ultimo_correlativo
  useEffect(() => {
    if (prefijo === undefined || ultimoCorrelativo === undefined || formulario.numero !== '') return
    const guardado = leerCorrelativoGuardado(prefijo, almacenDelNavegador())
    setValue('numero', proponerNumero({ prefijo, ultimoCorrelativo }, guardado))
  }, [prefijo, ultimoCorrelativo, formulario.numero, setValue])

  // --- precios, stock y pedido --------------------------------------------------------------
  const contexto: ContextoDePrecios = {
    clienteId: formulario.clienteId === '' ? undefined : formulario.clienteId,
    listaId: formulario.listaId === '' ? undefined : formulario.listaId,
    versionId: formulario.versionId === '' ? undefined : formulario.versionId,
    ubicacionId: ubicacionDeLaVenta,
  }
  const busqueda = useBuscarPrecios(contexto, textoDemorado, !esperandoJornada)
  const resultados: ProductoParaVender[] = busqueda.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const listaAplicada = busqueda.data?.pages[0]?.lista_id
  const listaParaVersiones = formulario.listaId === '' ? listaAplicada : formulario.listaId
  const versiones = useVersionesElegibles(listaParaVersiones, puedeElegirLista)

  const consultasDeItems = usePreciosDeProductos(
    contexto,
    items.map((item) => item.productoId),
  )
  const productos = new Map<string, ProductoConPrecio | undefined>()
  items.forEach((item, indice) => {
    const respuesta = consultasDeItems[indice]?.data
    const producto = respuesta?.items[0]
    productos.set(item.productoId, respuesta && producto ? aProductoConPrecio(producto, respuesta.version_id) : undefined)
  })
  const idDeLinea = (productoId: string, presentacionId: string) =>
    items.find((item) => item.productoId === productoId)?.idsDeLinea[presentacionId] ?? ''
  const pedido = armarPedido(items, productos, idDeLinea)

  // Los valores que el servidor resolvió y el usuario aceptó valen solo para este pedido (D2).
  const claveDelPedido = JSON.stringify([items.map((i) => [i.productoId, i.cajas, i.unidades]), contexto])
  const valoresVigentes = aceptados?.clave === claveDelPedido ? aceptados : null
  const envio = valoresVigentes
    ? aplicarValoresDelServidor(pedido.lineas, valoresVigentes.valores)
    : { lineas: pedido.lineas, total: pedido.total.toFixed(2) }

  const cobrado = sumarCobranzaDeVenta(medios).toFixed(2)
  const saldo = useSaldoDelCliente(formulario.clienteId === '' ? undefined : formulario.clienteId)
  const lecturaDeSaldo: LecturaDeSaldoDeCliente = saldo.isError
    ? { estado: 'error' }
    : saldo.isSuccess
      ? { estado: 'leido', saldo: saldo.data }
      : { estado: 'cargando' }
  const confirmacion = decidirConfirmacionDeVenta(lecturaDeSaldo, envio.total, cobrado)
  const esConsumidorFinal =
    (clientes.data?.pages.flatMap((pagina) => pagina.items) ?? []).find((c) => c.id === formulario.clienteId)?.es_consumidor_final ?? false
  const contadoDeConsumidorFinal = evaluarContadoDeConsumidorFinal(esConsumidorFinal, envio.total, cobrado)
  const esperandoSaldo = formulario.clienteId !== '' && confirmacion.tipo === 'esperar'

  const contextoDeVenta = {
    mediosQueRequierenReferencia: new Set((mediosPago.data?.items ?? []).filter((m) => m.requiere_referencia).map((m) => m.id)),
    ubicacionObligatoria: jornadaAbierta === null,
  }
  const habilitado =
    pedido.completo &&
    !esperandoJornada &&
    contadoDeConsumidorFinal.cumple &&
    puedeConfirmarVenta({ ...formulario, medios }, envio.lineas, contextoDeVenta)
  const operationIdPorContenido = useOperationIdPorContenido({
    formulario,
    lineas: envio.lineas,
    total: envio.total,
    ventaId,
    cobranzaId,
    conJornada: jornadaAbierta !== null,
  })
  const operationId = valoresVigentes?.operationId ?? operationIdPorContenido

  // --- acciones -----------------------------------------------------------------------------
  const agregarProducto = (producto: ProductoParaVender) => {
    const presentaciones = producto.presentaciones.map((p) => ({
      presentacionId: p.presentacion_id,
      nombre: p.nombre,
      unidadesBase: p.unidades_base,
      esReferencia: p.es_referencia,
    }))
    const inicial = cantidadInicialDeProducto(presentaciones)
    const idsDeLinea = Object.fromEntries(producto.presentaciones.map((p) => [p.presentacion_id, generarOperationId()]))
    setItems((actuales) =>
      actuales.some((item) => item.productoId === producto.producto_id)
        ? actuales
        : [...actuales, { productoId: producto.producto_id, nombre: producto.nombre, ...inicial, idsDeLinea }],
    )
  }
  const cambiarItem = (productoId: string, cambio: Partial<ItemDelPedido>) =>
    setItems((actuales) => actuales.map((item) => (item.productoId === productoId ? { ...item, ...cambio } : item)))
  const quitarItem = (productoId: string) => setItems((actuales) => actuales.filter((item) => item.productoId !== productoId))

  const limpiarErrores = () => {
    setErrorGeneral(null)
    setErroresDeCampo({})
    setErroresDeMedio({})
  }

  const alErrorDeVenta = async (error: ErrorDeVentas) => {
    if (error instanceof PermisoRequeridoVentasError) {
      setErrorGeneral('No tenés permiso para esta operación.')
      return
    }
    const valores = valoresDelServidorDe(error)
    if (valores !== null) {
      setPrecioDifiere({ valores, totalAnterior: envio.total })
      return
    }
    if (error.codigo === 'NUMERO_DUPLICADO') {
      const releida = await numeracion.refetch()
      const datos = releida.data
      if (datos !== undefined) {
        const guardado = leerCorrelativoGuardado(datos.prefijo, almacenDelNavegador())
        const nuevo = proponerTrasDuplicado(
          { prefijo: datos.prefijo, ultimoCorrelativo: datos.ultimo_correlativo },
          guardado,
          formulario.numero,
        )
        setErrorGeneral(`El número ${formulario.numero} ya fue usado. Propusimos ${nuevo}: revisalo y confirmá de nuevo.`)
        setValue('numero', nuevo)
        return
      }
    }
    if (error.medio !== null) {
      setErroresDeMedio({ [error.medio]: error.message })
      return
    }
    const campo = campoDelError(error)
    if (campo !== null) {
      const sinPrecio = error.codigo === 'PRODUCTO_SIN_PRECIO' ? productosSinPrecioDe(error) : []
      const detalle = sinPrecio.length > 0 ? ` Sin precio: ${sinPrecio.join(', ')}.` : ''
      setErroresDeCampo({ [campo]: `${error.message}${detalle}` })
      return
    }
    setErrorGeneral(error.message)
  }

  const enviar = async (lineas: typeof envio.lineas, total: string, idDeOperacion: string) => {
    setConfirmando(false)
    setPrecioDifiere(null)
    limpiarErrores()
    const solicitud = construirSolicitudDeVenta(
      { ...formulario, medios },
      lineas,
      total,
      ventaId,
      cobranzaId,
      jornadaAbierta === null,
    )
    try {
      const resultado = await confirmar.mutateAsync({ ...solicitud, operationId: idDeOperacion })
      const correlativo = correlativoDeNumero(resultado.numero, prefijo ?? '')
      if (prefijo !== undefined && correlativo !== null) guardarCorrelativo(prefijo, correlativo, almacenDelNavegador())
      setRegistrada(resultado)
    } catch (error) {
      if (error instanceof ErrorDeVentas) await alErrorDeVenta(error)
      else setErrorGeneral(MENSAJE_DE_RED)
    }
  }

  const alEnviar = (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    if (!habilitado || confirmar.isPending || esperandoSaldo) return
    if (confirmacion.tipo === 'saldo-a-favor' || confirmacion.tipo === 'saldo-ilegible') {
      setConfirmando(true)
      return
    }
    void enviar(envio.lineas, envio.total, operationId)
  }

  const aceptarValoresDelServidor = () => {
    if (precioDifiere === null) return
    const nuevos = aplicarValoresDelServidor(pedido.lineas, precioDifiere.valores)
    const aceptado: ValoresAceptados = { clave: claveDelPedido, valores: precioDifiere.valores, operationId: generarOperationId() }
    setAceptados(aceptado)
    void queryClient.invalidateQueries({ queryKey: clavesVentas.raiz() })
    void enviar(nuevos.lineas, nuevos.total, aceptado.operationId)
  }

  const cancelarPrecioDifiere = () => {
    setPrecioDifiere(null)
    void queryClient.invalidateQueries({ queryKey: clavesVentas.raiz() })
  }

  const cargarOtraVenta = () => {
    reset(VALORES_INICIALES)
    setItems([])
    setTextoProducto('')
    setAceptados(null)
    setVentaId(generarOperationId())
    setCobranzaId(generarOperationId())
    setRegistrada(null)
    ubicacionAutoElegida.current = false
    limpiarErrores()
  }

  const cambiarLista = (listaId: string) => {
    setValue('listaId', listaId)
    setValue('versionId', '')
  }
  const cambiarVersion = (versionId: string) => {
    if (versionId !== '' && formulario.listaId === '' && listaParaVersiones !== undefined) setValue('listaId', listaParaVersiones)
    setValue('versionId', versionId)
  }

  if (registrada) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Venta registrada" />
        <Card className="flex flex-col gap-2 text-sm text-primary">
          <p>
            La venta {registrada.numero} quedó confirmada por {formatearMonto(registrada.total)}.
          </p>
          <p data-testid="saldo-final">{textoDeSaldo('CLIENTE', registrada.saldo)}</p>
          <div className="flex flex-wrap gap-3">
            <Link to={`/admin/ventas/${registrada.venta_id}`} className="text-primary/70 hover:text-primary hover:underline">
              Ver la venta
            </Link>
            <Link to="/admin/ventas" className="text-primary/70 hover:text-primary hover:underline">
              Volver al listado
            </Link>
            <button type="button" className="text-primary/70 hover:text-primary hover:underline" onClick={cargarOtraVenta}>
              Cargar otra venta
            </button>
          </div>
        </Card>
      </main>
    )
  }

  const opcionesDeClientes = clientes.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const hayCliente = formulario.clienteId !== ''
  const totalAMostrar = parsearImporteDesdeApi(envio.total)
  const diferencias = precioDifiere === null ? [] : diferenciasConElServidor(envio.lineas, precioDifiere.valores)
  const nombreDeLinea = (lineaId: string) => {
    const visible = pedido.visibles.find((v) => v.linea.lineaId === lineaId)
    return visible ? `${visible.productoNombre} · ${visible.presentacionNombre}` : 'Línea'
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Nueva venta" />
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary/70">Registrar una venta desde acá requiere conexión: no se guarda para enviarla después.</p>
        {errorGeneral && <Alert>{errorGeneral}</Alert>}

        <Card className="flex flex-wrap items-end gap-3">
          <Campo id="venta-busqueda-cliente" etiqueta="Buscar cliente">
            <input
              id="venta-busqueda-cliente"
              className={CLASE_CONTROL}
              placeholder="Nombre o código"
              value={busquedaCliente}
              onChange={(evento) => setBusquedaCliente(evento.target.value)}
            />
          </Campo>
          <div data-testid="campo-cliente">
            <Campo id="venta-cliente" etiqueta="Cliente" error={erroresDeCampo.cliente}>
              <select
                id="venta-cliente"
                className={CLASE_CONTROL}
                value={formulario.clienteId}
                onChange={(evento) => setValue('clienteId', evento.target.value)}
              >
                <option value="">Elegí un cliente</option>
                {opcionesDeClientes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre}
                  </option>
                ))}
              </select>
            </Campo>
          </div>
          {contadoDeConsumidorFinal.aplica && (
            <p className="flex basis-full items-center gap-1 text-sm text-primary" data-testid="aviso-consumidor-final">
              {AVISO_CONSUMIDOR_FINAL_DE_CONTADO}
              <Ayuda clave="ventas.consumidorFinal" />
            </p>
          )}
          {hayCliente && (
            <div className="text-sm text-primary">
              {saldo.isPending && <p className="text-primary/70">Cargando saldo…</p>}
              {saldo.isError && <p className="text-danger">No se pudo leer el saldo del cliente.</p>}
              {saldo.isSuccess && <p data-testid="saldo-actual">{textoDeSaldo('CLIENTE', saldo.data)}</p>}
            </div>
          )}
          {jornadaAbierta !== null ? (
            <p className="text-sm text-primary" data-testid="ubicacion-de-jornada">
              Se vende desde la ubicación de tu jornada: {jornadaAbierta.ubicacion_nombre}
            </p>
          ) : (
            !esperandoJornada && (
              <div data-testid="campo-ubicacion">
                <Campo id="venta-ubicacion" etiqueta="Ubicación" error={erroresDeCampo.ubicacion}>
                  <select
                    id="venta-ubicacion"
                    className={CLASE_CONTROL}
                    value={formulario.ubicacionId}
                    onChange={(evento) => setValue('ubicacionId', evento.target.value)}
                  >
                    <option value="">Elegí la ubicación</option>
                    {ubicaciones.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.nombre}
                      </option>
                    ))}
                  </select>
                </Campo>
              </div>
            )
          )}
          {jornadaAbierta !== null && erroresDeCampo.ubicacion && <Alert>{erroresDeCampo.ubicacion}</Alert>}
        </Card>

        {puedeElegirLista && (
          <Card className="flex flex-wrap items-end gap-3" data-testid="bloque-lista">
            <Campo id="venta-lista" etiqueta="Lista de precios" ayuda="ventas.listaAnterior">
              <select
                id="venta-lista"
                className={CLASE_CONTROL}
                value={formulario.listaId}
                onChange={(evento) => cambiarLista(evento.target.value)}
              >
                <option value="">La del cliente</option>
                {(listas.data?.items ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nombre}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo id="venta-version" etiqueta="Versión">
              <select
                id="venta-version"
                className={CLASE_CONTROL}
                value={formulario.versionId}
                onChange={(evento) => cambiarVersion(evento.target.value)}
              >
                <option value="">La vigente</option>
                {(versiones.data ?? []).map((v) => (
                  <option key={v.version_id} value={v.version_id}>
                    {etiquetaDeVersion(v.numero, v.estado)}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo id="venta-motivo" etiqueta="Motivo">
              <select
                id="venta-motivo"
                className={CLASE_CONTROL}
                value={formulario.motivoId}
                onChange={(evento) => setValue('motivoId', evento.target.value)}
              >
                <option value="">Sin motivo</option>
                {(motivos.data?.items ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nombre}
                  </option>
                ))}
              </select>
            </Campo>
            {erroresDeCampo.lista && <Alert>{erroresDeCampo.lista}</Alert>}
          </Card>
        )}

        <BuscadorDeProductos
          texto={textoProducto}
          alCambiarTexto={setTextoProducto}
          resultados={resultados}
          cargando={busqueda.isPending && busqueda.fetchStatus !== 'idle'}
          hayMas={busqueda.hasNextPage}
          cargandoMas={busqueda.isFetchingNextPage}
          alCargarMas={() => void busqueda.fetchNextPage()}
          agregados={new Set(items.map((item) => item.productoId))}
          alAgregar={agregarProducto}
          hayCliente={hayCliente}
        />

        <div data-testid="campo-lineas" className="flex flex-col gap-2">
          {erroresDeCampo.lineas && <Alert>{erroresDeCampo.lineas}</Alert>}
          {items.length === 0 && <p className="text-sm text-primary/70">Todavía no cargaste productos.</p>}
          {items.map((item, indice) => {
            const consulta = consultasDeItems[indice]
            const producto = productos.get(item.productoId)
            const presentaciones = producto?.presentaciones ?? []
            const estado = consulta?.isError
              ? 'No se pudo leer el precio de este producto.'
              : consulta?.isSuccess && producto === undefined
                ? 'El producto ya no se ofrece en esta lista.'
                : producto === undefined
                  ? 'Cargando precio…'
                  : undefined
            return (
              <ItemDeVenta
                key={item.productoId}
                productoId={item.productoId}
                nombre={item.nombre}
                cajas={item.cajas}
                unidades={item.unidades}
                admiteCajas={admiteCajas(presentaciones)}
                admiteUnidadesSueltas={admiteUnidadesSueltas(presentaciones)}
                lineas={pedido.visibles.filter((v) => v.linea.productoId === item.productoId)}
                error={pedido.errores[item.productoId]}
                avisoDeStock={
                  pedido.superaStock.includes(item.productoId)
                    ? 'Supera el stock disponible en la ubicación. Solo se puede vender con permiso de stock negativo.'
                    : undefined
                }
                estado={estado}
                alCambiarCajas={(cajas) => cambiarItem(item.productoId, { cajas })}
                alCambiarUnidades={(unidades) => cambiarItem(item.productoId, { unidades })}
                alQuitar={() => quitarItem(item.productoId)}
              />
            )
          })}
        </div>

        <div data-testid="bloque-cobranza" className="flex flex-col gap-2">
          {contadoDeConsumidorFinal.aplica && !contadoDeConsumidorFinal.cumple && (
            <p className="text-sm text-danger" data-testid="contado-consumidor-final">
              {FALTA_CONTADO_DE_CONSUMIDOR_FINAL}
            </p>
          )}
          <MediosDeCobranza
            titulo="Cobranza en el acto (opcional)"
            ayudaDelBloque="ventas.cobranza"
            idsDeFilas={mediosField.fields.map((campo) => campo.id)}
            medios={medios}
            mediosDePago={mediosPago.data?.items ?? []}
            registrar={(indice, campo) => register(`medios.${indice}.${campo}` as const)}
            alAgregar={() => mediosField.append(MEDIO_VACIO)}
            alQuitar={(indice) => mediosField.remove(indice)}
            erroresDeMedio={erroresDeMedio}
            permitirQuitarTodos
            pie={
              <p className="text-sm text-primary" data-testid="cobrado">
                Cobrado en el acto: {formatearMonto(cobrado)}
              </p>
            }
          />
          {medios.length > 0 && (
            <Campo id="venta-observacion-cobranza" etiqueta="Observación del cobro (opcional)">
              <input id="venta-observacion-cobranza" className={CLASE_CONTROL} maxLength={500} {...register('observacionCobranza')} />
            </Campo>
          )}
          {erroresDeCampo.cobranza && <Alert>{erroresDeCampo.cobranza}</Alert>}
        </div>

        <Card className="flex flex-col gap-2 text-sm text-primary">
          <div data-testid="campo-numero">
            <Campo id="venta-numero" etiqueta="Número de venta" ayuda="ventas.numero" error={erroresDeCampo.numero}>
              <input id="venta-numero" className={`${CLASE_CONTROL} w-48`} {...register('numero')} />
            </Campo>
          </div>
          <p data-testid="total-de-la-venta" className="text-base font-semibold">
            Total: {formatearMonto(totalAMostrar.toFixed(2))}
          </p>
          {saldo.isSuccess && (
            <p data-testid="saldo-resultante">
              Saldo después de la venta: {textoDeSaldoResultanteDeVenta(saldo.data, envio.total, cobrado)}
            </p>
          )}
        </Card>

        <div className="flex gap-2">
          <Boton type="submit" disabled={!habilitado || confirmar.isPending || esperandoSaldo}>
            Confirmar venta
          </Boton>
          <Link to="/admin/ventas" className="self-center text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>

      <Dialogo abierto={confirmando} titulo="Confirmar venta" onCerrar={() => setConfirmando(false)}>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-primary">
            {confirmacion.tipo === 'saldo-a-favor' || confirmacion.tipo === 'saldo-ilegible' ? confirmacion.mensaje : null}
          </p>
          <p className="text-sm text-primary/70">
            Ese saldo se descuenta solo de la próxima compra del cliente. Si no es lo que querés, revisá lo cobrado.
          </p>
          <div className="flex gap-2">
            <Boton onClick={() => void enviar(envio.lineas, envio.total, operationId)}>Aceptar y registrar</Boton>
            <Boton variante="secundario" onClick={() => setConfirmando(false)}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>

      <Dialogo abierto={precioDifiere !== null} titulo="Cambió el precio" onCerrar={cancelarPrecioDifiere}>
        {precioDifiere !== null && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-primary">
              Mientras armabas la venta cambió el precio o el total. Revisá los valores nuevos antes de confirmar.
            </p>
            <ul className="flex flex-col gap-1 text-sm text-primary">
              {diferencias
                .filter((d) => d.cambio)
                .map((d) => (
                  <li key={d.lineaId}>
                    {nombreDeLinea(d.lineaId)}: {formatearMonto(d.brutoAnterior)} pasa a {formatearMonto(d.brutoNuevo)} (precio de
                    referencia {formatearMonto(d.precioNuevo)})
                  </li>
                ))}
            </ul>
            <p className="text-sm font-semibold text-primary">
              Total: {formatearMonto(precioDifiere.totalAnterior)} pasa a {formatearMonto(precioDifiere.valores.total)}
            </p>
            <div className="flex gap-2">
              <Boton onClick={aceptarValoresDelServidor}>Confirmar con los valores nuevos</Boton>
              <Boton variante="secundario" onClick={cancelarPrecioDifiere}>
                Cancelar
              </Boton>
            </div>
          </div>
        )}
      </Dialogo>
    </main>
  )
}

export default VentaFormScreen
