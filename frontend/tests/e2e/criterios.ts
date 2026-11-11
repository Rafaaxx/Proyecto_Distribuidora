/**
 * Mapa de cobertura de los 12 criterios de éxito de `00` §9 (change 28, D15): cada criterio con el
 * archivo (relativo a la raíz del repositorio) que lo prueba. La prueba de Vitest
 * `tests/unit/cobertura/criteriosDeAceptacion.test.ts` falla nombrando el criterio si falta en la
 * lista o si su archivo no existe. Es un módulo sin dependencias de Playwright para que Vitest lo
 * pueda importar.
 *
 * El criterio 12 (restaurar una copia en un entorno limpio) no lo corre el navegador: lo cubren las
 * pruebas de infraestructura del change 27b y la prueba manual (D15). Lo que la emulación no
 * reemplaza (un teléfono real, el envío por WhatsApp) va también a la prueba manual.
 */
export interface Criterio {
  numero: number
  titulo: string
  /** Archivos de prueba, desde la raíz del repositorio. */
  archivos: readonly string[]
}

const E2E = 'frontend/tests/e2e'

export const CRITERIOS: readonly Criterio[] = [
  { numero: 1, titulo: 'Importación y saldos iniciales', archivos: [`${E2E}/01-importacion.spec.ts`] },
  { numero: 2, titulo: 'Compra a crédito con presentaciones y costos distintos', archivos: [`${E2E}/02-compra.spec.ts`] },
  {
    numero: 3,
    titulo: 'Nueva versión de lista sin alterar ventas anteriores',
    archivos: [`${E2E}/03-lista-de-precios.spec.ts`],
  },
  { numero: 4, titulo: 'Transferencia al vehículo y apertura de jornada', archivos: [`${E2E}/04-jornada.spec.ts`] },
  {
    numero: 5,
    titulo: 'Venta sin conexión con descuentos y cobro parcial',
    archivos: [`${E2E}/05-venta-sin-conexion.spec.ts`],
  },
  { numero: 6, titulo: 'Exceso de crédito sin conexión', archivos: [`${E2E}/06-exceso-de-credito.spec.ts`] },
  { numero: 7, titulo: 'Nota de venta sin señal', archivos: [`${E2E}/07-nota-sin-senal.spec.ts`] },
  { numero: 8, titulo: 'Doble sincronización deliberada', archivos: [`${E2E}/08-doble-sincronizacion.spec.ts`] },
  { numero: 9, titulo: 'Anulación sin borrar historia', archivos: [`${E2E}/09-anulacion.spec.ts`] },
  { numero: 10, titulo: 'Rendición con diferencia auditada', archivos: [`${E2E}/10-rendicion.spec.ts`] },
  { numero: 11, titulo: 'El reporte concilia', archivos: [`${E2E}/11-reporte.spec.ts`] },
  {
    numero: 12,
    titulo: 'Restauración de una copia en un entorno limpio',
    archivos: ['backend/tests/infra/test_restauracion.py', 'backend/tests/infra/test_prueba_restauracion.py'],
  },
]

/**
 * Los números de los criterios del 1 al 12 que no tienen prueba: faltan en la lista, no declaran
 * ningún archivo o alguno de sus archivos no existe. En orden ascendente.
 */
export function criteriosSinPrueba(criterios: readonly Criterio[], existe: (archivo: string) => boolean): number[] {
  const sinPrueba: number[] = []
  for (let numero = 1; numero <= 12; numero += 1) {
    const criterio = criterios.find((c) => c.numero === numero)
    if (criterio === undefined || criterio.archivos.length === 0 || !criterio.archivos.every(existe)) {
      sinPrueba.push(numero)
    }
  }
  return sinPrueba
}
