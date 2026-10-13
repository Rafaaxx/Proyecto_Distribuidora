import { Route, Routes } from 'react-router-dom'

import { AjusteDetalleScreen } from './AjusteDetalleScreen'
import { AjusteFormScreen } from './AjusteFormScreen'
import { AjustesListScreen } from './AjustesListScreen'
import { JornadaAbrirScreen } from './JornadaAbrirScreen'
import { JornadaDetalleScreen } from './JornadaDetalleScreen'
import { JornadasListScreen } from './JornadasListScreen'
import { KardexScreen } from './KardexScreen'
import { StockInicialScreen } from './StockInicialScreen'
import { StockPorUbicacionScreen } from './StockPorUbicacionScreen'
import { TransferenciaDetalleScreen } from './TransferenciaDetalleScreen'
import { TransferenciaFormScreen } from './TransferenciaFormScreen'
import { TransferenciasListScreen } from './TransferenciasListScreen'
import { UbicacionesListScreen } from './UbicacionesListScreen'
import { UbicacionFormScreen } from './UbicacionFormScreen'

/**
 * Router del área de stock dentro de `/admin` (change 09, grupo 8, tareas 8.2 a
 * 8.4; `design.md` D15). Se carga en diferido desde `AdminScreen`, mismo criterio
 * que `ClientesArea`/`ProveedoresArea`. Una sola sección del menú, "Stock"
 * (`TRANSFERIR_STOCK`, D3); cada pantalla decide sus acciones con su permiso.
 *
 * Change 14 (grupo 13): Transferencias (`TRANSFERIR_STOCK`) y Ajustes (`AJUSTAR_STOCK`) cuelgan de
 * la misma sección; sus accesos están en el listado de ubicaciones y cada pantalla decide con su
 * permiso (D11). `/transferencias/nueva` y `/ajustes/nueva` van antes que su `:id`.
 *
 * Change 15 (grupo 14): Jornadas (`ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, D15/D16)
 * cuelga de la misma sección; `/jornadas/abrir` va antes que su `:jornadaId`.
 *
 * `/ubicaciones/nueva` se declara antes que `/ubicaciones/:ubicacionId` (mismo
 * criterio que `/nuevo` en `ClientesArea`).
 */
export function StockArea() {
  return (
    <Routes>
      <Route path="/" element={<UbicacionesListScreen />} />
      <Route path="/ubicaciones/nueva" element={<UbicacionFormScreen />} />
      <Route path="/ubicaciones/:ubicacionId" element={<UbicacionFormScreen />} />
      <Route path="/ubicaciones/:ubicacionId/stock" element={<StockPorUbicacionScreen />} />
      <Route path="/ubicaciones/:ubicacionId/kardex/:productoId" element={<KardexScreen />} />
      <Route path="/ubicaciones/:ubicacionId/stock-inicial" element={<StockInicialScreen />} />
      <Route path="/transferencias" element={<TransferenciasListScreen />} />
      <Route path="/transferencias/nueva" element={<TransferenciaFormScreen />} />
      <Route path="/transferencias/:transferenciaId" element={<TransferenciaDetalleScreen />} />
      <Route path="/ajustes" element={<AjustesListScreen />} />
      <Route path="/ajustes/nueva" element={<AjusteFormScreen />} />
      <Route path="/ajustes/:ajusteId" element={<AjusteDetalleScreen />} />
      <Route path="/jornadas" element={<JornadasListScreen />} />
      <Route path="/jornadas/abrir" element={<JornadaAbrirScreen />} />
      <Route path="/jornadas/:jornadaId" element={<JornadaDetalleScreen />} />
    </Routes>
  )
}

export default StockArea
