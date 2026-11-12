import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  formatearImporteDeReporte,
  formatearSaldoDeCuenta,
  formatearTotalAFavor,
} from '../../../domain/reportes/presentacion'
import type { ClienteConSaldo, ProveedorConSaldo } from '../../../features/reportes/api'
import type {
  FiltroDeSaldo,
  FiltrosDeSaldosDeClientes,
  FiltrosDeSaldosDeProveedores,
} from '../../../features/reportes/claves'
import { useReporteDeSaldosDeClientes, useReporteDeSaldosDeProveedores } from '../../../features/reportes/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { Paginacion } from './Paginacion'
import {
  CLASE_CONTROL,
  EstadoDelReporte,
  Rotulo,
  Tarjeta,
  TituloDePestana,
} from './piezas'
import { usePaginas, useTextoConRetraso } from './usoDeFiltros'

/** Los textos de los estados de cliente y de proveedor son los que ya usan sus listados. */
const ETIQUETA_DE_ESTADO: Readonly<Record<string, string>> = {
  ACTIVO: 'Activo',
  SUSPENDIDO: 'Suspendido',
  INACTIVO: 'Inactivo',
}

const OPCIONES_DE_SALDO: readonly (readonly [FiltroDeSaldo, string])[] = [
  ['CON_SALDO', 'Con saldo'],
  ['DEUDORES', 'Deudores'],
  ['A_FAVOR', 'A favor'],
  ['TODOS', 'Todos'],
]

const etiquetaDeEstado = (estado: string) => ETIQUETA_DE_ESTADO[estado] ?? estado

function FiltroDeSaldoSelect({ valor, onCambio }: { valor: FiltroDeSaldo | undefined; onCambio: (v: FiltroDeSaldo | undefined) => void }) {
  return (
    <Rotulo id="filtro-saldo" etiqueta="Saldo">
      <select
        id="filtro-saldo"
        className={CLASE_CONTROL}
        value={valor ?? 'CON_SALDO'}
        // «Con saldo» es lo que el servidor usa sin filtro: no viaja.
        onChange={(e) => onCambio(e.target.value === 'CON_SALDO' ? undefined : (e.target.value as FiltroDeSaldo))}
      >
        {OPCIONES_DE_SALDO.map(([valorOpcion, etiqueta]) => (
          <option key={valorOpcion} value={valorOpcion}>
            {etiqueta}
          </option>
        ))}
      </select>
    </Rotulo>
  )
}

function FiltroDeEstado({
  estados,
  valor,
  onCambio,
}: {
  estados: readonly string[]
  valor: string | undefined
  onCambio: (v: string | undefined) => void
}) {
  return (
    <Rotulo id="filtro-estado" etiqueta="Estado">
      <select
        id="filtro-estado"
        className={CLASE_CONTROL}
        value={valor ?? ''}
        onChange={(e) => onCambio(e.target.value || undefined)}
      >
        <option value="">Todos</option>
        {estados.map((estado) => (
          <option key={estado} value={estado}>
            {etiquetaDeEstado(estado)}
          </option>
        ))}
      </select>
    </Rotulo>
  )
}

function FiltroDeBusqueda({ valor, onCambio }: { valor: string; onCambio: (v: string) => void }) {
  return (
    <Rotulo id="filtro-buscar" etiqueta="Buscar">
      <input
        id="filtro-buscar"
        type="search"
        className={CLASE_CONTROL}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
      />
    </Rotulo>
  )
}

function Totales({ adeudado, aFavor }: { adeudado: string; aFavor: string }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Tarjeta etiqueta="Total adeudado" valor={formatearImporteDeReporte(adeudado)} />
      <Tarjeta etiqueta="Total a favor" valor={formatearTotalAFavor(aFavor)} />
    </div>
  )
}

/** Saldos de clientes (D8, D11; CC-04, INV-13): filtros, totales y tabla; el enlace a la cuenta según permiso. */
export function SaldosDeClientesReporte() {
  const [filtros, setFiltros] = useState<FiltrosDeSaldosDeClientes>({})
  const [busqueda, setBusqueda] = useState('')
  const texto = useTextoConRetraso(busqueda).trim()
  const consulta: FiltrosDeSaldosDeClientes = { ...filtros, ...(texto === '' ? {} : { texto }) }
  // Cambiar el saldo, el vendedor, el estado o la búsqueda vuelve a la página 1 (D14).
  const [{ pagina }, irAPagina] = usePaginas(JSON.stringify(consulta), { pagina: 1 })
  const reporte = useReporteDeSaldosDeClientes({ ...consulta, pagina })
  const datos = reporte.data
  // El servidor trae todos los vendedores con clientes, sin importar la página ni los filtros.
  const vendedores = datos?.vendedores ?? []

  const columnas: ColumnaTabla<ClienteConSaldo>[] = [
    { clave: 'codigo', encabezado: 'Código', render: (c) => c.codigo ?? '' },
    { clave: 'razon', encabezado: 'Razón social', render: (c) => c.razon_social ?? c.nombre },
    { clave: 'vendedor', encabezado: 'Vendedor', render: (c) => c.vendedor_nombre ?? '' },
    { clave: 'estado', encabezado: 'Estado', render: (c) => etiquetaDeEstado(c.estado) },
    {
      clave: 'limite',
      encabezado: 'Límite',
      render: (c) => (c.limite_credito === null ? 'Sin límite' : formatearImporteDeReporte(c.limite_credito)),
    },
    { clave: 'saldo', encabezado: 'Saldo', render: (c) => formatearSaldoDeCuenta(c.saldo) },
    {
      clave: 'disponible',
      encabezado: 'Disponible',
      render: (c) => (c.disponible === null ? '' : formatearImporteDeReporte(c.disponible)),
    },
    {
      clave: 'cuenta',
      encabezado: '',
      render: (c) => (
        <SiTienePermiso permiso="GESTIONAR_CLIENTES">
          <Link
            to={`/admin/clientes/${c.cliente_id}/cuenta-corriente`}
            className="text-sm text-primary/70 hover:text-primary hover:underline"
          >
            Ver estado de cuenta
          </Link>
        </SiTienePermiso>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <TituloDePestana titulo="Saldos de clientes" ayuda="reportes.saldos" />
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <FiltroDeSaldoSelect valor={filtros.saldo} onCambio={(saldo) => setFiltros((f) => ({ ...f, saldo }))} />
          <Rotulo id="filtro-vendedor" etiqueta="Vendedor">
            <select
              id="filtro-vendedor"
              className={CLASE_CONTROL}
              value={filtros.vendedorId ?? ''}
              onChange={(e) => setFiltros((f) => ({ ...f, vendedorId: e.target.value || undefined }))}
            >
              <option value="">Todos</option>
              {vendedores.map(({ id, nombre }) => (
                <option key={id} value={id}>
                  {nombre}
                </option>
              ))}
            </select>
          </Rotulo>
          <FiltroDeEstado
            estados={['ACTIVO', 'SUSPENDIDO', 'INACTIVO']}
            valor={filtros.estado}
            onCambio={(estado) => setFiltros((f) => ({ ...f, estado: estado as FiltrosDeSaldosDeClientes['estado'] }))}
          />
          <FiltroDeBusqueda valor={busqueda} onCambio={setBusqueda} />
        </div>
      </Card>

      <EstadoDelReporte cargando={reporte.isPending} error={reporte.error} />
      {datos !== undefined && !reporte.isError && (
        <>
          <Totales adeudado={datos.total_adeudado} aFavor={datos.total_a_favor} />
          {datos.clientes.total_filas === 0 ? (
            <p className="text-sm text-primary/70">Sin clientes para mostrar.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Tabla
                  etiqueta="Saldos de clientes"
                  filas={datos.clientes.filas}
                  columnas={columnas}
                  obtenerClave={(c) => c.cliente_id}
                />
              </div>
              <Paginacion
                pagina={datos.clientes.pagina}
                paginas={datos.clientes.paginas}
                alCambiar={(nueva) => irAPagina('pagina', nueva)}
                etiqueta="Saldos de clientes"
              />
            </>
          )}
        </>
      )}
    </div>
  )
}

/**
 * Saldos de proveedores (D8 = B, D11; CC-04, SEG-06). Se monta solo detrás de la regla compuesta (`ReportesArea`):
 * sin ella no se pide nada.
 */
export function SaldosDeProveedoresReporte() {
  const [filtros, setFiltros] = useState<FiltrosDeSaldosDeProveedores>({})
  const [busqueda, setBusqueda] = useState('')
  const texto = useTextoConRetraso(busqueda).trim()
  const consulta: FiltrosDeSaldosDeProveedores = { ...filtros, ...(texto === '' ? {} : { texto }) }
  const [{ pagina }, irAPagina] = usePaginas(JSON.stringify(consulta), { pagina: 1 })
  const reporte = useReporteDeSaldosDeProveedores({ ...consulta, pagina }, true)
  const datos = reporte.data

  const columnas: ColumnaTabla<ProveedorConSaldo>[] = [
    { clave: 'proveedor', encabezado: 'Proveedor', render: (p) => p.nombre },
    { clave: 'estado', encabezado: 'Estado', render: (p) => etiquetaDeEstado(p.estado) },
    { clave: 'saldo', encabezado: 'Saldo', render: (p) => formatearSaldoDeCuenta(p.saldo) },
    {
      clave: 'cuenta',
      encabezado: '',
      render: (p) => (
        <SiTienePermiso permiso="GESTIONAR_PROVEEDORES">
          <Link
            to={`/admin/proveedores/${p.proveedor_id}/cuenta-corriente`}
            className="text-sm text-primary/70 hover:text-primary hover:underline"
          >
            Ver estado de cuenta
          </Link>
        </SiTienePermiso>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <TituloDePestana titulo="Saldos de proveedores" ayuda="reportes.saldos" />
      <Card>
        <div className="flex flex-wrap items-start gap-3">
          <FiltroDeSaldoSelect valor={filtros.saldo} onCambio={(saldo) => setFiltros((f) => ({ ...f, saldo }))} />
          <FiltroDeEstado
            estados={['ACTIVO', 'INACTIVO']}
            valor={filtros.estado}
            onCambio={(estado) => setFiltros((f) => ({ ...f, estado: estado as FiltrosDeSaldosDeProveedores['estado'] }))}
          />
          <FiltroDeBusqueda valor={busqueda} onCambio={setBusqueda} />
        </div>
      </Card>

      <EstadoDelReporte cargando={reporte.isPending} error={reporte.error} />
      {datos !== undefined && !reporte.isError && (
        <>
          <Totales adeudado={datos.total_adeudado} aFavor={datos.total_a_favor} />
          {datos.proveedores.total_filas === 0 ? (
            <p className="text-sm text-primary/70">Sin proveedores para mostrar.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Tabla
                  etiqueta="Saldos de proveedores"
                  filas={datos.proveedores.filas}
                  columnas={columnas}
                  obtenerClave={(p) => p.proveedor_id}
                />
              </div>
              <Paginacion
                pagina={datos.proveedores.pagina}
                paginas={datos.proveedores.paginas}
                alCambiar={(nueva) => irAPagina('pagina', nueva)}
                etiqueta="Saldos de proveedores"
              />
            </>
          )}
        </>
      )}
    </div>
  )
}
