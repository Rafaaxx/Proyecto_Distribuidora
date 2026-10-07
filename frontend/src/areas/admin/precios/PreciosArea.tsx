import { Route, Routes } from 'react-router-dom'

import { BorradorScreen } from './BorradorScreen'
import { ListaDetalleScreen } from './ListaDetalleScreen'
import { ListaFormScreen } from './ListaFormScreen'
import { ListasListScreen } from './ListasListScreen'
import { VersionScreen } from './VersionScreen'

/**
 * Router del área de listas de precios dentro de `/admin` (change 13, grupo 13). Se carga en
 * diferido desde `AdminScreen`, mismo criterio que `PagosArea`. Una sola sección del menú,
 * "Listas de precios" (`GESTIONAR_LISTAS` o `PUBLICAR_LISTAS`, ADR-027); cada pantalla decide
 * sus acciones con su permiso. `/nueva` se declara antes que `/:listaId`.
 */
export function PreciosArea() {
  return (
    <Routes>
      <Route path="/" element={<ListasListScreen />} />
      <Route path="/nueva" element={<ListaFormScreen />} />
      <Route path="/:listaId" element={<ListaDetalleScreen />} />
      <Route path="/:listaId/editar" element={<ListaFormScreen />} />
      <Route path="/:listaId/borrador" element={<BorradorScreen />} />
      <Route path="/:listaId/versiones/:versionId" element={<VersionScreen />} />
    </Routes>
  )
}

export default PreciosArea
