import { useRef, useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import type { ImportacionDelHistorial, ImportacionResultado } from '../../../features/importacion/api'
import { resolverOperationId, type EnvioPendiente } from '../../../features/importacion/envio'
import {
  ErrorDeImportacion,
  PermisoRequeridoImportacionError,
  type ErrorDeFilaDeImportacion,
} from '../../../features/importacion/errores'
import {
  esErrorDeRed,
  useDescargarPlantilla,
  useHistorialDeImportaciones,
  useImportarArchivo,
} from '../../../features/importacion/hooks'
import { TIPOS_DE_IMPORTACION, ayudaDeTipo, etiquetaDeTipo } from '../../../features/importacion/tipos'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { generarOperationId } from '../../../lib/api/operationId'
import { formatearFechaHoraEnZona } from '../../../lib/fecha'

const SIN_PERMISO = 'No tenés permiso para importar datos.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'
const MENSAJE_GENERICO = 'No se pudo completar la operación.'
const AVISO_NADA_IMPORTADO = 'No se importó ninguna fila'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

const COLUMNAS_DE_ERRORES: ColumnaTabla<ErrorDeFilaDeImportacion>[] = [
  { clave: 'fila', encabezado: 'Fila', render: (e) => String(e.fila) },
  { clave: 'columna', encabezado: 'Columna', render: (e) => e.columna ?? '—' },
  { clave: 'codigo', encabezado: 'Código', render: (e) => e.codigo },
  { clave: 'mensaje', encabezado: 'Mensaje', render: (e) => e.mensaje },
]

function textoDeFilasImportadas(resultado: ImportacionResultado): string {
  const cantidad = resultado.filas_ok
  return `${String(cantidad)} ${cantidad === 1 ? 'fila importada' : 'filas importadas'}`
}

function mensajeDeError(error: unknown): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  if (error instanceof PermisoRequeridoImportacionError) return SIN_PERMISO
  if (error instanceof ErrorDeImportacion && error.errores.length > 0) {
    const cantidad = error.errores.length
    return `La importación tiene ${String(cantidad)} ${cantidad === 1 ? 'error' : 'errores'}.`
  }
  return error instanceof ErrorDeImportacion ? error.message : MENSAJE_GENERICO
}

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Importación" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Pantalla de importación de `/admin/importacion` (change 10, grupo 8, tareas 8.1 y 8.2;
 * spec `administracion-de-importaciones`). Visible solo con `IMPORTAR_DATOS`, de `['yo']`
 * vía `<SiTienePermiso>` (ADR-027): sin él, nada se monta ni se pide.
 *
 * Elegir el tipo, descargar su plantilla, seleccionar un CSV o `.xlsx` e importarlo. La
 * pantalla NO lee ni valida el contenido del archivo: lo sube tal cual y el servidor valida
 * todo (TR-10). Si el servidor rechaza la importación, muestra todos los errores por fila en
 * una tabla (o el error de archivo como mensaje general) y deja claro que no se importó
 * ninguna fila (INV-01). Cada archivo seleccionado tiene su `Operation-Id`, que se reutiliza
 * si el usuario reintenta tras un corte de red y se renueva con otro archivo, otro tipo o
 * después de una respuesta del servidor (SYN-02, INV-06). Debajo, el historial paginado
 * (TR-04: fechas en la zona de la organización).
 */
export function ImportacionScreen() {
  return (
    <SiTienePermiso permiso="IMPORTAR_DATOS" fallback={<SinPermiso />}>
      <Importacion />
    </SiTienePermiso>
  )
}

function Importacion() {
  const importar = useImportarArchivo()
  const plantilla = useDescargarPlantilla()
  const [tipo, setTipo] = useState<string>(TIPOS_DE_IMPORTACION[0].valor)
  const [archivo, setArchivo] = useState<File | null>(null)
  const [claveDelArchivo, setClaveDelArchivo] = useState(0)
  const [resultado, setResultado] = useState<ImportacionResultado | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [puedeReintentar, setPuedeReintentar] = useState(false)
  // Envío cortado por la red antes de recibir respuesta: su `Operation-Id` se conserva
  // para reenviarlo si el usuario reintenta lo mismo.
  const pendienteRef = useRef<EnvioPendiente | null>(null)

  function limpiarResultado() {
    setResultado(null)
    setError(null)
    setPuedeReintentar(false)
  }

  async function enviar() {
    if (archivo === null) return
    limpiarResultado()
    plantilla.reset()
    const operationId = resolverOperationId(pendienteRef.current, tipo, archivo, generarOperationId)
    try {
      const aceptado = await importar.mutateAsync({ tipo, archivo, operationId })
      pendienteRef.current = null
      setResultado(aceptado)
      setArchivo(null)
      setClaveDelArchivo((clave) => clave + 1)
    } catch (errorDeEnvio) {
      // Corte de red: puede que el servidor sí lo haya procesado, así que se reenvía con el
      // mismo `Operation-Id`. Un rechazo con respuesta HTTP ya está resuelto: reenviar es
      // una operación nueva.
      const deRed = esErrorDeRed(errorDeEnvio)
      pendienteRef.current = deRed ? { tipo, archivo, operationId } : null
      setPuedeReintentar(deRed)
      setError(errorDeEnvio)
    }
  }

  function descargar() {
    limpiarResultado()
    plantilla.mutate(tipo)
  }

  const errorDePlantilla: unknown = plantilla.error
  const errorMostrado = error ?? errorDePlantilla
  const errorDeFilas = error instanceof ErrorDeImportacion ? error.errores : []
  const rechazadoPorElServidor = error instanceof ErrorDeImportacion

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Importación" />
      <Card>
        <form
          onSubmit={(evento) => {
            evento.preventDefault()
            void enviar()
          }}
          className="flex flex-col gap-4"
        >
          <p className="text-sm text-primary/70">
            Subí una planilla CSV o Excel (.xlsx). Se importa completa o no se importa nada: si alguna fila tiene un
            error, ves todos los errores y no se carga ninguna fila. Este paso necesita conexión con el servidor.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-primary">
              Tipo de importación
              <select
                className={CLASE_CONTROL}
                value={tipo}
                onChange={(evento) => {
                  setTipo(evento.target.value)
                  limpiarResultado()
                }}
              >
                {TIPOS_DE_IMPORTACION.map((opcion) => (
                  <option key={opcion.valor} value={opcion.valor}>
                    {opcion.etiqueta}
                  </option>
                ))}
              </select>
            </label>
            <Boton type="button" variante="secundario" onClick={descargar} disabled={plantilla.isPending}>
              Descargar plantilla
            </Boton>
          </div>
          {ayudaDeTipo(tipo) !== null && (
            <p role="note" className="text-sm text-primary/70">
              {ayudaDeTipo(tipo)}
            </p>
          )}
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-primary">
              Archivo
              <input
                key={claveDelArchivo}
                type="file"
                accept=".csv,.xlsx"
                className={CLASE_CONTROL}
                onChange={(evento) => {
                  setArchivo(evento.target.files?.[0] ?? null)
                  limpiarResultado()
                }}
              />
            </label>
            <Boton type="submit" disabled={archivo === null || importar.isPending}>
              Importar
            </Boton>
            {puedeReintentar && (
              <Boton type="button" variante="secundario" disabled={importar.isPending} onClick={() => void enviar()}>
                Reintentar
              </Boton>
            )}
          </div>

          {resultado !== null && (
            <p role="status" className="text-sm font-medium text-primary">
              {textoDeFilasImportadas(resultado)}
            </p>
          )}

          {errorMostrado !== null && errorMostrado !== undefined && (
            <Alert>
              {mensajeDeError(errorMostrado)}
              {rechazadoPorElServidor && (
                <>
                  {' '}
                  <strong>{AVISO_NADA_IMPORTADO}</strong>
                </>
              )}
            </Alert>
          )}

          {errorDeFilas.length > 0 && (
            <Tabla
              etiqueta="Errores de la importación"
              filas={errorDeFilas}
              columnas={COLUMNAS_DE_ERRORES}
              obtenerClave={(e) => `${String(e.fila)}-${e.columna ?? ''}-${e.codigo}`}
            />
          )}
        </form>
      </Card>

      <Historial />
    </main>
  )
}

function Historial() {
  const historial = useHistorialDeImportaciones()
  const paginas = historial.data?.pages ?? []
  const filas = paginas.flatMap((pagina) => pagina.items)
  const zona = paginas[0]?.zona_horaria ?? 'UTC'

  const columnas: ColumnaTabla<ImportacionDelHistorial>[] = [
    { clave: 'fecha', encabezado: 'Fecha', render: (i) => formatearFechaHoraEnZona(i.registered_at, zona) },
    { clave: 'tipo', encabezado: 'Tipo', render: (i) => etiquetaDeTipo(i.tipo) },
    { clave: 'archivo', encabezado: 'Archivo', render: (i) => i.archivo_nombre },
    { clave: 'filas', encabezado: 'Filas importadas', render: (i) => String(i.filas_ok) },
    { clave: 'usuario', encabezado: 'Usuario', render: (i) => i.usuario_nombre ?? '—' },
  ]

  return (
    <Card>
      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold text-primary">Historial de importaciones</h2>
        {historial.isError && <Alert>No se pudo obtener el historial de importaciones.</Alert>}
        {historial.isSuccess && filas.length === 0 && (
          <p className="text-sm text-primary/70">Todavía no hay importaciones.</p>
        )}
        {filas.length > 0 && (
          <Tabla
            etiqueta="Historial de importaciones"
            filas={filas}
            columnas={columnas}
            obtenerClave={(i) => i.id}
          />
        )}
        {historial.hasNextPage && (
          <div>
            <Boton
              type="button"
              variante="secundario"
              disabled={historial.isFetchingNextPage}
              onClick={() => void historial.fetchNextPage()}
            >
              Cargar más
            </Boton>
          </div>
        )}
      </section>
    </Card>
  )
}

export default ImportacionScreen
