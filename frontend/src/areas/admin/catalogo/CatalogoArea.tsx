import { Navigate, Route, Routes } from 'react-router-dom'

import { CategoriasYMarcasScreen } from './CategoriasYMarcasScreen'
import { ProductoFormScreen } from './ProductoFormScreen'
import { ProductosListScreen } from './ProductosListScreen'

/**
 * Router del área de catálogo dentro de `/admin` (tarea 10.1). Se carga en
 * diferido desde `AdminScreen` (`AppRoutes.tsx` ya hace lo mismo entre
 * `/ruta` y `/admin`): el bundle de catálogo no se descarga hasta que
 * alguien navega a `/admin/catalogo`.
 */
export function CatalogoArea() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="productos" replace />} />
      <Route path="productos" element={<ProductosListScreen />} />
      <Route path="productos/nuevo" element={<ProductoFormScreen />} />
      <Route path="productos/:productoId" element={<ProductoFormScreen />} />
      <Route path="categorias-y-marcas" element={<CategoriasYMarcasScreen />} />
    </Routes>
  )
}

export default CatalogoArea
