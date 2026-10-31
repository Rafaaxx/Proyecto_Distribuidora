import { calcularVenta, ErrorDeCalculoDeVenta, type LineaCalculo, type ResultadoVenta } from '../calculo'
import { ErrorDeDescuentos } from '../descuentos/errores'
import { ErrorDeBrutoDeLinea } from '../precios/brutoDeLinea'
import type { AutorizadorCredito } from '../credito/evaluacion'
import type { MedioDePagoDeFormulario } from '../pagos-proveedores/formularioPago'
import { CantidadInvalidaError } from '../stock/cantidades'
import {
  autorizacionesNecesarias,
  completarSeleccion,
  type AutorizadorDeContexto,
  type SeleccionDeAutorizadores,
  type TipoDeAutorizacion,
} from '../ventas/autorizacionDeVenta'
import {
  evaluarContadoDeConsumidorFinal,
  sumarCobranzaDeVenta,
  type ContadoDeConsumidorFinal,
} from '../ventas/calculoDeVenta'
import { evaluarPanelDeCredito, textoDeDecisionDeCredito, type PanelDeCredito } from '../ventas/creditoDeVenta'
import {
  leerPorcentaje,
  mayorPorcentajeManual,
  motivoFalta,
  necesidadDeAutorizacionDeDescuento,
  reglaDelMotorDesdeApi,
  type ContextoDeDescuento,
  type DescuentoDeLinea,
  type NecesidadDeDescuento,
} from '../ventas/descuentosDeVenta'
import { construirSolicitudDeVenta, puedeConfirmarVenta, type LineaDelPedido } from '../ventas/formularioVenta'
import { congelarNotaDeVenta } from '../ventas/notaDesdeLocal'
import { armarPedido, type ItemDelPedido, type ProductoConPrecio, type PedidoArmado } from '../ventas/pedido'
import type { components } from '../../api/schema.gen'
import type {
  AutorizadorLocal,
  CatalogoLocal,
  ClienteLocal,
  ConfiguracionLocal,
  ListaLocal,
  MovimientoLocal,
  NotaCongelada,
  PrecioLocal,
  PresentacionLocal,
  ProductoLocal,
  ReglaDescuentoLocal,
  SesionLocal,
  StockLocal,
  VersionLocal,
} from '../../lib/dispositivo/db'
import { parsearImporteDesdeApi } from '../../lib/money'
import type { EntradaDeConfirmacion } from '../../sync/confirmarVentaLocal'
import { creditoDeConsumidorFinal, bloqueoPorCliente, bloqueoPorConsumidorFinal, bloqueoPorLista, puedeElegirOtraLista, versionesElegiblesComoAnterior } from './reglasDeVentaLocal'
import { armarCreditoDeRuta } from './creditoDeRuta'
import { saldoConsiderado as calcularSaldoConsiderado, stockDisponible } from './disponiblesLocales'
import { versionVigente } from './lecturasLocales'
import { evaluarStockDeVenta, type EvaluacionDeStock } from './stockDeVenta'

/**
 * Armado de la venta de `/ruta` (change 22a, `design.md` D1, D6 a D10, D14, D15; PRC-22, VTA-04,
 * DSC-05, DSC-06, CLI-02, CLI-03, CRE-06 a CRE-09, STK-06, INV-03, INV-04). Funciones PURAS: de la
 * instantánea de la base local y del carrito salen el pedido, los totales, los avisos, los
 * bloqueos y, al confirmar, la entrada de la transacción atómica. Los componentes solo pintan.
 * Importes siempre como string; las cantidades, enteros en unidad base.
 */
type Esquema = components['schemas']
export type MedioPagoLocal = Extract<CatalogoLocal, { clave: 'medios_pago' }>['items'][number]
export type MotivoLocal = Extract<CatalogoLocal, { clave: 'motivos' }>['items'][number]

/** Todo lo que la venta lee de la base local (más los movimientos de la jornada). */
export interface DatosParaVender {
  sesion: SesionLocal
  configuracion: ConfiguracionLocal
  clientes: ClienteLocal[]
  productos: ProductoLocal[]
  presentaciones: PresentacionLocal[]
  listas: ListaLocal[]
  versiones: VersionLocal[]
  precios: PrecioLocal[]
  reglas: ReglaDescuentoLocal[]
  stock: StockLocal[]
  mediosPago: MedioPagoLocal[]
  motivos: MotivoLocal[]
  autorizadores: AutorizadorLocal[]
  movimientos: MovimientoLocal[]
}

export interface ItemDeCarrito extends ItemDelPedido {
  /** Identificador de línea por presentación, generado al agregar y estable en los reintentos. */
  idsDeLinea: Record<string, string>
}

/** El carrito vive solo en memoria (VTA-07, D12). */
export interface CarritoDeRuta {
  ventaId: string
  cobranzaId: string
  /** UUIDv7 del comando; se reutiliza al reintentar (INV-06). */
  operationId: string
  clienteId: string
  listaId: string
  versionId: string
  motivoListaId: string
  items: ItemDeCarrito[]
  generalTexto: string
  propios: Record<string, string>
  motivoDescuentoId: string
  medios: MedioDePagoDeFormulario[]
  observacionCobranza: string
  aceptaExceso: boolean
  seleccion: SeleccionDeAutorizadores
  /** Confirmación expresa de "Vender igual" (D6 = C, solo con `PERMITIR_STOCK_NEGATIVO`). */
  venderIgual: boolean
}

export interface LineaArmada {
  lineaId: string
  productoId: string
  productoNombre: string
  presentacionNombre: string
  cantidad: number
  cantidadBase: number
  bruto: string
  descuentos: DescuentoDeLinea[]
  descuentoTotal: string
  neto: string
  /** Aviso "Supera el stock del vehículo (quedan N)" de la línea, si corresponde. */
  avisoDeStock: string | null
}

export interface InfoDeLista {
  /** El usuario tiene `USAR_LISTA_ANTERIOR` (PRC-21): se ofrece elegir otra lista o versión. */
  ofreceOtra: boolean
  listaId: string | null
  listaNombre: string | null
  versionId: string | null
  versionNumero: number | null
  usaOtra: boolean
  listas: ListaLocal[]
  versionesElegibles: VersionLocal[]
}

export interface VentaArmada {
  cliente: ClienteLocal | null
  lista: InfoDeLista
  lineas: LineaArmada[]
  erroresPorProducto: Record<string, string>
  total: string
  cobrado: string
  saldoConsiderado: string
  /** Nulo para el consumidor final. */
  saldoResultante: string | null
  stock: EvaluacionDeStock
  contadoDeConsumidorFinal: ContadoDeConsumidorFinal
  /** Nulo para el consumidor final o sin cliente. */
  panelDeCredito: PanelDeCredito | null
  contextoDeDescuento: ContextoDeDescuento | null
  puedeDarDescuento: boolean
  necesidadDeDescuento: NecesidadDeDescuento
  faltaMotivoDeDescuento: boolean
  errorDelGeneral: string | null
  erroresDePropios: Record<string, string>
  autorizacionesNecesarias: TipoDeAutorizacion[]
  autorizadores: AutorizadorDeContexto[]
  /** Quién autoriza cada cosa: lo elegido o, si hay un único supervisor posible, ese. */
  seleccion: SeleccionDeAutorizadores
  /** Motivos por los que no se puede confirmar (textos para el usuario). */
  bloqueos: string[]
  puedeConfirmar: boolean
  /** Para armar la confirmación; nulo si el cálculo falló. */
  calculo: ResultadoVenta | null
  pedido: PedidoArmado
  descuentoGeneral: string | null
}

const NUMERO_PROVISIONAL = 'PROV-000000'
export const PERMISO_SUPERAR_CREDITO = 'SUPERAR_CREDITO'
export const PERMISO_AUTORIZAR_DESCUENTO_LOCAL = 'AUTORIZAR_DESCUENTO'

function permisoDe(tipo: TipoDeAutorizacion): string {
  return tipo === 'DESCUENTO' ? PERMISO_AUTORIZAR_DESCUENTO_LOCAL : PERMISO_SUPERAR_CREDITO
}

/** Permiso que se exige al verificar el PIN de un supervisor para esa autorización (D10). */
export function permisoRequeridoPara(tipo: TipoDeAutorizacion): string {
  return permisoDe(tipo)
}

function autorizadoresDeContexto(autorizadores: readonly AutorizadorLocal[]): AutorizadorDeContexto[] {
  return autorizadores.map((a) => ({
    id: a.id,
    nombre: a.nombre,
    puedeAutorizarDescuento: a.permisos.includes(PERMISO_AUTORIZAR_DESCUENTO_LOCAL),
    puedeSuperarCredito: a.permisos.includes(PERMISO_SUPERAR_CREDITO),
  }))
}

function esVigente(regla: ReglaDescuentoLocal, ahora: Date): boolean {
  const t = ahora.getTime()
  return new Date(regla.vigencia_desde).getTime() <= t && (regla.vigencia_hasta === null || new Date(regla.vigencia_hasta).getTime() > t)
}

function resolverLista(datos: DatosParaVender, cliente: ClienteLocal | null, carrito: CarritoDeRuta, ahora: Date) {
  const permisos = datos.sesion.permisos
  const ofreceOtra = puedeElegirOtraLista(permisos)
  const predeterminada = datos.listas.find((l) => l.es_predeterminada)
  const delCliente = datos.listas.find((l) => l.id === cliente?.lista_precio_id) ?? predeterminada
  const elegida = ofreceOtra && carrito.listaId !== '' ? datos.listas.find((l) => l.id === carrito.listaId) : undefined
  const lista = elegida ?? delCliente
  const versionesDeLista = lista === undefined ? [] : datos.versiones.filter((v) => v.lista_id === lista.id)
  const vigente = versionVigente(versionesDeLista, ahora)
  const versionElegida =
    ofreceOtra && carrito.versionId !== '' ? versionesDeLista.find((v) => v.id === carrito.versionId) : undefined
  const version: VersionLocal | null = versionElegida ?? vigente
  const usaOtraLista = elegida !== undefined && elegida.id !== delCliente?.id
  const usaOtraVersion = versionElegida !== undefined && versionElegida.id !== vigente?.id
  const info: InfoDeLista = {
    ofreceOtra,
    listaId: lista?.id ?? null,
    listaNombre: lista?.nombre ?? null,
    versionId: version?.id ?? null,
    versionNumero: version?.numero ?? null,
    usaOtra: usaOtraLista || usaOtraVersion,
    listas: datos.listas,
    versionesElegibles: versionesElegiblesComoAnterior(versionesDeLista, ahora),
  }
  return { info, version, elegida: usaOtraLista || usaOtraVersion ? elegida : undefined, versionElegida }
}

function mensajeDeError(error: unknown): string | null {
  if (
    error instanceof ErrorDeCalculoDeVenta ||
    error instanceof ErrorDeDescuentos ||
    error instanceof ErrorDeBrutoDeLinea ||
    error instanceof CantidadInvalidaError
  ) {
    return error.message
  }
  return null
}

const STOCK_VACIO: EvaluacionDeStock = { lineas: [], confirmacion: 'libre', mensaje: null }

export function armarVentaDeRuta(datos: DatosParaVender, carrito: CarritoDeRuta, ahora: Date): VentaArmada {
  const permisos = datos.sesion.permisos
  const jornadaId = datos.sesion.jornada.id
  const cliente = datos.clientes.find((c) => c.id === carrito.clienteId) ?? null
  const { info: lista, version } = resolverLista(datos, cliente, carrito, ahora)
  const bloqueos: string[] = []

  // --- pedido y precios (PRC-22, VTA-10) -------------------------------------------------------
  const productoPorId = new Map(datos.productos.map((p) => [p.id, p]))
  const preciosDeVersion = new Map(
    datos.precios.filter((p) => version !== null && p.version_id === version.id).map((p) => [p.producto_id, p]),
  )
  const productos = new Map<string, ProductoConPrecio | undefined>()
  for (const item of carrito.items) {
    const producto = productoPorId.get(item.productoId)
    if (producto === undefined) {
      productos.set(item.productoId, undefined)
      continue
    }
    const precio = preciosDeVersion.get(producto.id)
    productos.set(item.productoId, {
      productoId: producto.id,
      nombre: producto.nombre,
      precioReferencia: precio?.precio_referencia ?? null,
      unidadesReferencia: precio?.unidades_referencia ?? null,
      // El stock lo evalúa `evaluarStockDeVenta` (D6 = C): acá no hay aviso de la gemela de /admin.
      stockBase: null,
      categoriaId: producto.categoria_id,
      marcaId: producto.marca_id ?? undefined,
      listaVersionId: version?.id ?? '',
      presentaciones: datos.presentaciones
        .filter((pr) => pr.producto_id === producto.id)
        .map((pr) => ({ presentacionId: pr.id, nombre: pr.nombre, unidadesBase: pr.unidades_base, esReferencia: pr.es_referencia })),
    })
  }
  const idsPorProducto = new Map(carrito.items.map((i) => [i.productoId, i.idsDeLinea]))
  const pedido = armarPedido(carrito.items, productos, (productoId, presentacionId) => idsPorProducto.get(productoId)?.[presentacionId] ?? '')
  const erroresPorProducto = pedido.errores
  const hayErrores = Object.keys(erroresPorProducto).length > 0

  // --- descuentos (DSC-05, DSC-06) -------------------------------------------------------------
  const manual = datos.sesion.contexto_venta?.descuento_manual ?? null
  const contextoDeDescuento: ContextoDeDescuento | null =
    manual === null
      ? null
      : { habilitado: manual.habilitado, motivoObligatorio: manual.motivo_obligatorio, tienePermiso: manual.tiene_permiso, tope: manual.tope, puedeAutorizar: manual.puede_autorizar }
  const puedeDarDescuento = contextoDeDescuento !== null && contextoDeDescuento.habilitado && contextoDeDescuento.tienePermiso
  const generalLeido = leerPorcentaje(carrito.generalTexto)
  const general = puedeDarDescuento && generalLeido.valido ? generalLeido.fraccion : null
  const erroresDePropios: Record<string, string> = {}
  const propioDe = (lineaId: string): string | null => {
    const leido = leerPorcentaje(carrito.propios[lineaId] ?? '')
    if (!puedeDarDescuento) return null
    if (!leido.valido) {
      erroresDePropios[lineaId] = leido.mensaje
      return null
    }
    return leido.fraccion
  }
  const errorDelGeneral = puedeDarDescuento && !generalLeido.valido ? generalLeido.mensaje : null
  const reglasDelMotor = datos.reglas.filter((r) => esVigente(r, ahora)).map(reglaDelMotorDesdeApi)

  // --- cálculo de la venta (VTA-04) ------------------------------------------------------------
  const cantidadBaseDeLinea = new Map(pedido.visibles.map((v) => [v.linea.lineaId, v.cantidadBase]))
  const lineasDeCalculo: LineaCalculo[] = pedido.lineas.map((linea) => {
    const producto = productoPorId.get(linea.productoId)
    return {
      id: linea.lineaId,
      precioReferencia: linea.precioReferencia,
      unidadesReferencia: linea.unidadesReferencia,
      cantidadBase: cantidadBaseDeLinea.get(linea.lineaId) ?? 0,
      alicuota: producto?.alicuota_valor ?? '0.000000',
      productoId: linea.productoId,
      categoriaId: producto?.categoria_id ?? '',
      marcaId: producto?.marca_id ?? '',
      descuentoManual: propioDe(linea.lineaId),
    }
  })

  let calculo: ResultadoVenta | null = null
  let errorDeCalculo: string | null = null
  if (pedido.lineas.length > 0 && !hayErrores) {
    try {
      calculo = calcularVenta(datos.configuracion.modo_impositivo, lineasDeCalculo, reglasDelMotor, general)
    } catch (error) {
      errorDeCalculo = mensajeDeError(error)
      if (errorDeCalculo === null) throw error
    }
  }
  const total = calculo === null ? '0.00' : calculo.total.toFixed(2)

  const resultadoPorLinea = new Map(calculo?.lineas.map((l) => [l.id, l]) ?? [])
  const mayorManual = mayorPorcentajeManual(
    (calculo?.lineas ?? []).flatMap((l) => l.descuentos.filter((d) => d.origen === 'MANUAL').map((d) => d.porcentaje?.toFixed(6) ?? null)),
  )

  // --- disponibles locales (D5) y stock (D6 = C) ------------------------------------------------
  const stockBase = new Map(datos.stock.map((s) => [s.producto_id, s.cantidad_base]))
  const disponiblePorProducto = new Map<string, number>()
  for (const item of carrito.items) {
    disponiblePorProducto.set(
      item.productoId,
      stockDisponible(stockBase.get(item.productoId) ?? 0, datos.movimientos, item.productoId, jornadaId),
    )
  }
  const stock =
    pedido.visibles.length === 0
      ? STOCK_VACIO
      : evaluarStockDeVenta(
          pedido.visibles.map((v) => ({ lineaId: v.linea.lineaId, productoId: v.linea.productoId, cantidadBase: v.cantidadBase })),
          disponiblePorProducto,
          permisos,
        )
  const avisoPorLinea = new Map(stock.lineas.map((l) => [l.lineaId, l.aviso]))

  const lineas: LineaArmada[] = pedido.visibles.map((v) => {
    const resultado = resultadoPorLinea.get(v.linea.lineaId)
    const descuentos: DescuentoDeLinea[] = (resultado?.descuentos ?? []).map((d) => ({
      origen: d.origen,
      reglaId: d.reglaId,
      porcentaje: d.porcentaje === null ? null : d.porcentaje.toFixed(6),
      importe: d.importe.toFixed(2),
    }))
    return {
      lineaId: v.linea.lineaId,
      productoId: v.linea.productoId,
      productoNombre: v.productoNombre,
      presentacionNombre: v.presentacionNombre,
      cantidad: v.linea.cantidad,
      cantidadBase: v.cantidadBase,
      bruto: v.linea.importeBruto,
      descuentos,
      descuentoTotal: resultado?.descuentoTotal.toFixed(2) ?? '0.00',
      neto: resultado?.neto.toFixed(2) ?? v.linea.importeBruto,
      avisoDeStock: avisoPorLinea.get(v.linea.lineaId) ?? null,
    }
  })

  // --- cobranza, cliente y saldo ----------------------------------------------------------------
  const cobrado = sumarCobranzaDeVenta(carrito.medios).toFixed(2)
  const saldoConsiderado =
    cliente === null ? '0.00' : calcularSaldoConsiderado(cliente.saldo, datos.movimientos, cliente.id, jornadaId)
  const esConsumidorFinal = cliente?.es_consumidor_final ?? false
  const contadoDeConsumidorFinal = evaluarContadoDeConsumidorFinal(esConsumidorFinal, total, cobrado)
  const saldoResultante =
    cliente === null || esConsumidorFinal
      ? null
      : parsearImporteDesdeApi(saldoConsiderado).plus(parsearImporteDesdeApi(total)).minus(parsearImporteDesdeApi(cobrado)).toFixed(2)

  // --- crédito sin conexión (D9) ----------------------------------------------------------------
  const panelDeCredito =
    cliente === null || esConsumidorFinal
      ? null
      : evaluarPanelDeCredito({
          datos: {
            limite: cliente.credito.limite,
            saldo: saldoConsiderado,
            politica: cliente.credito.politica,
            toleranciaTipo: cliente.credito.tolerancia_tipo,
            toleranciaValor: cliente.credito.tolerancia_valor,
          },
          total,
          cobranza: cobrado,
          aceptaExceso: carrito.aceptaExceso,
          puedeSuperar: datos.sesion.contexto_venta?.puede_superar_credito ?? false,
          modo: 'SIN_CONEXION',
        })
  const decisionDeCredito = panelDeCredito?.decision ?? 'sin-control'

  // --- autorizaciones (D10) ---------------------------------------------------------------------
  const necesidadDeDescuento: NecesidadDeDescuento =
    contextoDeDescuento === null ? { estado: 'sin-descuento' } : necesidadDeAutorizacionDeDescuento(mayorManual, contextoDeDescuento)
  const faltaMotivoDeDescuento = contextoDeDescuento === null ? false : motivoFalta(mayorManual, contextoDeDescuento, carrito.motivoDescuentoId)
  const necesarias = autorizacionesNecesarias(necesidadDeDescuento, decisionDeCredito)
  const autorizadores = autorizadoresDeContexto(datos.autorizadores)
  const seleccion = completarSeleccion(necesarias, autorizadores, carrito.seleccion)
  const seleccionCompleta = necesarias.every((tipo) => {
    const id = seleccion[tipo]
    return id !== undefined && id !== '' && autorizadores.some((a) => a.id === id && (tipo === 'DESCUENTO' ? a.puedeAutorizarDescuento : a.puedeSuperarCredito))
  })

  // --- bloqueos ---------------------------------------------------------------------------------
  const agregar = (texto: string | null) => {
    if (texto !== null && !bloqueos.includes(texto)) bloqueos.push(texto)
  }
  if (cliente === null) agregar('Elegí un cliente.')
  if (cliente !== null) agregar(bloqueoPorCliente(cliente, permisos))
  for (const mensaje of Object.values(erroresPorProducto)) agregar(mensaje)
  agregar(errorDeCalculo)
  if (cliente !== null) agregar(bloqueoPorConsumidorFinal(cliente, total, cobrado))
  agregar(
    bloqueoPorLista({
      usaOtraVersion: lista.usaOtra,
      motivoObligatorio: datos.configuracion.motivo_obligatorio_lista,
      motivoId: carrito.motivoListaId,
    }),
  )
  agregar(stock.mensaje)
  if (stock.confirmacion === 'vender-igual' && !carrito.venderIgual) agregar('Confirmá "Vender igual" para vender más del stock del vehículo.')
  if (errorDelGeneral !== null || Object.keys(erroresDePropios).length > 0) agregar('Revisá los porcentajes de descuento.')
  if (necesidadDeDescuento.estado === 'deshabilitado' || necesidadDeDescuento.estado === 'sin-permiso') {
    agregar('No podés dar descuentos manuales.')
  }
  if (faltaMotivoDeDescuento) agregar('Elegí el motivo del descuento.')
  if (panelDeCredito !== null && (decisionDeCredito === 'bloqueado' || decisionDeCredito === 'pide-aceptar')) {
    agregar(textoDeDecisionDeCredito(panelDeCredito))
  }
  if (necesarias.length > 0 && !seleccionCompleta) agregar('Elegí el supervisor que autoriza.')

  const formularioValido =
    cliente !== null &&
    puedeConfirmarVenta(
      {
        clienteId: carrito.clienteId,
        ubicacionId: '',
        numero: NUMERO_PROVISIONAL,
        listaId: '',
        versionId: '',
        motivoId: '',
        observacionCobranza: carrito.observacionCobranza,
        medios: carrito.medios,
      },
      pedido.lineas,
      {
        mediosQueRequierenReferencia: new Set(datos.mediosPago.filter((m) => m.requiere_referencia).map((m) => m.id)),
        ubicacionObligatoria: false,
      },
    )
  if (cliente !== null && !formularioValido && pedido.lineas.length > 0 && !hayErrores) {
    agregar('Revisá los medios de cobro: elegí el medio, el importe y la referencia donde se pide.')
  }
  if (pedido.lineas.length === 0 && cliente !== null && !hayErrores) agregar('Cargá al menos un producto.')

  return {
    cliente,
    lista,
    lineas,
    erroresPorProducto,
    total,
    cobrado,
    saldoConsiderado,
    saldoResultante,
    stock,
    contadoDeConsumidorFinal,
    panelDeCredito,
    contextoDeDescuento,
    puedeDarDescuento,
    necesidadDeDescuento,
    faltaMotivoDeDescuento,
    errorDelGeneral,
    erroresDePropios,
    autorizacionesNecesarias: necesarias,
    autorizadores,
    seleccion,
    bloqueos,
    puedeConfirmar: bloqueos.length === 0 && calculo !== null,
    calculo,
    pedido,
    descuentoGeneral: general,
  }
}

/** Lo que cambia entre el armado y la confirmación: quién, desde qué teléfono y qué PIN se verificó. */
export interface ContextoDeConfirmacion {
  usuarioId: string
  dispositivoId: string
  ahora: Date
  appVersion: string
  /** Ids de los supervisores cuyo PIN ya se verificó en el teléfono (grupo 9). */
  autorizadoresVerificados: readonly string[]
}

function textoONulo(texto: string): string | null {
  const recortado = texto.trim()
  return recortado === '' ? null : recortado
}

/**
 * La entrada de `confirmarVentaLocal`: contenido del comando sin credenciales (el PIN nunca
 * viaja, ADR-056), crédito completo (CRE-09) y datos congelados de la nota (D15). Lanza si la
 * venta no se puede confirmar o si falta el PIN verificado de un supervisor que la autoriza.
 */
export function armarConfirmacionDeRuta(
  datos: DatosParaVender,
  carrito: CarritoDeRuta,
  armada: VentaArmada,
  contexto: ContextoDeConfirmacion,
): EntradaDeConfirmacion {
  const { cliente, calculo } = armada
  if (!armada.puedeConfirmar || cliente === null || calculo === null) {
    throw new Error('La venta no se puede confirmar: ' + (armada.bloqueos[0] ?? 'faltan datos.'))
  }

  const seleccionFinal = (tipo: TipoDeAutorizacion): string | null => {
    if (!armada.autorizacionesNecesarias.includes(tipo)) return null
    const id = armada.seleccion[tipo]
    if (id === undefined || id === '' || !contexto.autorizadoresVerificados.includes(id)) {
      throw new Error('Falta verificar el PIN del supervisor que autoriza.')
    }
    return id
  }
  const descuentoAutorizadorId = seleccionFinal('DESCUENTO')
  const creditoAutorizadorId = seleccionFinal('CREDITO')

  let autorizadorDeCredito: AutorizadorCredito | null = null
  if (creditoAutorizadorId !== null) {
    const local = datos.autorizadores.find((a) => a.id === creditoAutorizadorId)
    if (local === undefined) throw new Error('El supervisor elegido no está en los datos del teléfono.')
    autorizadorDeCredito = { usuarioId: local.id, permisos: local.permisos }
  }

  const credito = cliente.es_consumidor_final
    ? creditoDeConsumidorFinal(armada.saldoConsiderado, armada.total, armada.cobrado)
    : armarCreditoDeRuta({
        limite: cliente.credito.limite,
        saldoConsiderado: armada.saldoConsiderado,
        politica: cliente.credito.politica,
        toleranciaTipo: cliente.credito.tolerancia_tipo,
        toleranciaValor: cliente.credito.tolerancia_valor,
        total: armada.total,
        cobranza: armada.cobrado,
        aceptaExceso: carrito.aceptaExceso,
        usuarioId: contexto.usuarioId,
        permisosUsuario: datos.sesion.contexto_venta?.puede_superar_credito === true ? [PERMISO_SUPERAR_CREDITO] : [],
        autorizador: autorizadorDeCredito,
      })

  const lineasDelPedido: LineaDelPedido[] = armada.pedido.lineas
  const porLinea = new Map(
    armada.lineas.map((l) => [
      l.lineaId,
      { propio: textoDelPropio(carrito, l.lineaId, armada), descuentos: l.descuentos },
    ]),
  )
  const hayManual = armada.lineas.some((l) => l.descuentos.some((d) => d.origen === 'MANUAL'))
  const contenido: Esquema['VentaConfirmarRequest'] = {
    ...construirSolicitudDeVenta(
      {
        clienteId: carrito.clienteId,
        ubicacionId: '',
        numero: NUMERO_PROVISIONAL,
        listaId: armada.lista.usaOtra ? (armada.lista.listaId ?? '') : '',
        versionId: armada.lista.usaOtra ? (armada.lista.versionId ?? '') : '',
        motivoId: armada.lista.usaOtra ? carrito.motivoListaId : '',
        observacionCobranza: carrito.observacionCobranza,
        medios: carrito.medios,
      },
      lineasDelPedido,
      armada.total,
      carrito.ventaId,
      carrito.cobranzaId,
      false,
      {
        descuentoGeneral: hayManual ? armada.descuentoGeneral : null,
        motivoDescuentoId: hayManual && carrito.motivoDescuentoId !== '' ? carrito.motivoDescuentoId : null,
        descuentoAutorizadorId,
        aceptaExceso: false,
        creditoAutorizadorId: null,
        porLinea,
      },
    ),
    credito,
  }

  const congelada: NotaCongelada = congelarNotaDeVenta({
    organizacion: {
      nombre: datos.configuracion.nombre,
      cuit: datos.configuracion.cuit,
      domicilio: datos.configuracion.nota.domicilio,
      telefono: datos.configuracion.nota.telefono,
    },
    zonaHoraria: datos.configuracion.zona_horaria,
    muestraSaldo: datos.configuracion.nota.muestra_saldo,
    modoImpositivo: datos.configuracion.modo_impositivo,
    vendedorNombre: datos.sesion.usuario.nombre,
    cliente: {
      nombre: cliente.nombre,
      razon_social: cliente.razon_social,
      documento_tipo: cliente.documento_tipo,
      documento_numero: cliente.documento_numero,
      direccion: textoONulo(cliente.direccion),
      es_consumidor_final: cliente.es_consumidor_final,
    },
    lineas: armada.lineas.map((l) => ({
      lineaId: l.lineaId,
      productoNombre: l.productoNombre,
      presentacionNombre: l.presentacionNombre,
      unidadesPresentacion: datos.presentaciones.find((p) => p.nombre === l.presentacionNombre && p.producto_id === l.productoId)?.unidades_base ?? 1,
    })),
    medios: carrito.medios.map((m) => ({
      medioPagoId: m.medioPagoId,
      nombre: datos.mediosPago.find((x) => x.id === m.medioPagoId)?.nombre ?? '—',
    })),
    saldoConsiderado: armada.saldoConsiderado,
    total: armada.total,
    cobrado: armada.cobrado,
  })

  return {
    contenido,
    calculo,
    lineas: armada.lineas.map((l) => ({ lineaId: l.lineaId, productoId: l.productoId, cantidadBase: l.cantidadBase })),
    operationId: carrito.operationId,
    usuarioId: contexto.usuarioId,
    dispositivoId: contexto.dispositivoId,
    ahora: contexto.ahora,
    appVersion: contexto.appVersion,
    nota: congelada,
  }
}

/** El porcentaje propio de la línea como fracción (solo si se puede dar descuento y es válido). */
function textoDelPropio(carrito: CarritoDeRuta, lineaId: string, armada: VentaArmada): string | null {
  if (!armada.puedeDarDescuento) return null
  const leido = leerPorcentaje(carrito.propios[lineaId] ?? '')
  return leido.valido ? leido.fraccion : null
}
