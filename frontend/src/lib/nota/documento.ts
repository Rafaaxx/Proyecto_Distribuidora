/**
 * Definición del documento PDF de la nota de venta (change 20, tarea 2.2; VTA-13, ADR-008;
 * `design.md` D7, D14). Función pura: convierte el `ContenidoDeNota` ya formateado en la
 * definición que consume pdfmake; no importa pdfmake (solo sus tipos), así se prueba sin generar
 * el PDF. Página A4 vertical.
 */

import type { Content, TableCell, TDocumentDefinitions } from 'pdfmake/interfaces'

import type { ContenidoDeNota } from '../../domain/ventas/notaDeVenta'

const ANCHOS_DE_LINEAS = [90, '*', 62, 62, 58, 62]

function encabezado(nota: ContenidoDeNota): Content {
  return {
    columns: [
      {
        width: '*',
        stack: [
          { text: nota.organizacion.nombre, style: 'organizacion' },
          ...nota.organizacion.renglones.map((renglon): Content => ({ text: renglon, style: 'secundario' })),
        ],
      },
      {
        width: 'auto',
        alignment: 'right',
        stack: [
          { text: nota.titulo, style: 'titulo' },
          { text: nota.numero, bold: true },
          { text: nota.fechaHora, style: 'secundario' },
          { text: `Vendedor: ${nota.vendedor}`, style: 'secundario' },
        ],
      },
    ],
  }
}

function bloqueDeCliente(nota: ContenidoDeNota): Content {
  return {
    margin: [0, 12, 0, 0],
    stack: [
      { text: 'Cliente', style: 'rotulo' },
      { text: nota.cliente.nombre, bold: true },
      ...nota.cliente.renglones.map((renglon): Content => ({ text: renglon, style: 'secundario' })),
    ],
  }
}

function bloqueDeAnulacion(nota: ContenidoDeNota): Content[] {
  if (nota.anulacion === null) return []
  return [
    {
      margin: [0, 10, 0, 0],
      stack: nota.anulacion.renglones.map((renglon): Content => ({ text: renglon, color: '#b91c1c', bold: true })),
    },
  ]
}

function tablaDeLineas(nota: ContenidoDeNota): Content {
  const derecha = (texto: string, estilo?: string): TableCell => ({ text: texto, alignment: 'right', style: estilo })
  const cabecera: TableCell[] = nota.columnas.map((columna, indice) =>
    indice >= 2 ? derecha(columna, 'cabecera') : { text: columna, style: 'cabecera' },
  )
  return {
    margin: [0, 14, 0, 0],
    table: {
      headerRows: 1,
      widths: ANCHOS_DE_LINEAS,
      body: [
        cabecera,
        ...nota.lineas.map((linea): TableCell[] => [
          linea.cantidad,
          linea.producto,
          derecha(linea.precio),
          derecha(linea.bruto),
          derecha(linea.descuento),
          derecha(linea.importe),
        ]),
      ],
    },
    layout: 'lightHorizontalLines',
  }
}

function tablaDeTotales(nota: ContenidoDeNota): Content {
  return {
    margin: [0, 10, 0, 0],
    alignment: 'right',
    table: {
      widths: ['*', 110],
      body: nota.totales.map((total): TableCell[] => [
        { text: total.rotulo, alignment: 'right', bold: total.destacado, fontSize: total.destacado ? 12 : 10 },
        { text: total.valor, alignment: 'right', bold: total.destacado, fontSize: total.destacado ? 12 : 10 },
      ]),
    },
    layout: 'noBorders',
  }
}

function bloqueDeCobranza(nota: ContenidoDeNota): Content {
  const { cobranza } = nota
  if (cobranza.total === null) return { margin: [0, 12, 0, 0], text: cobranza.rotulo, bold: true }
  return {
    margin: [0, 12, 0, 0],
    stack: [
      { columns: [{ text: cobranza.rotulo, bold: true }, { text: cobranza.total, alignment: 'right', bold: true }] },
      ...cobranza.medios.map(
        (medio): Content => ({
          columns: [{ text: medio.nombre, style: 'secundario' }, { text: medio.importe, alignment: 'right', style: 'secundario' }],
        }),
      ),
    ],
  }
}

function bloqueDeSaldo(nota: ContenidoDeNota): Content[] {
  if (nota.saldo === null) return []
  return [
    {
      margin: [0, 8, 0, 0],
      columns: [{ text: nota.saldo.rotulo, bold: true }, { text: nota.saldo.valor, alignment: 'right', bold: true }],
    },
  ]
}

export function documentoDeNota(nota: ContenidoDeNota): TDocumentDefinitions {
  return {
    pageSize: 'A4',
    pageOrientation: 'portrait',
    pageMargins: [40, 40, 40, 60],
    info: { title: `${nota.titulo} ${nota.numero}` },
    defaultStyle: { font: 'Roboto', fontSize: 10 },
    styles: {
      titulo: { fontSize: 16, bold: true },
      organizacion: { fontSize: 13, bold: true },
      rotulo: { fontSize: 8, color: '#6b7280', bold: true },
      secundario: { fontSize: 9, color: '#374151' },
      cabecera: { bold: true, fontSize: 9 },
    },
    ...(nota.anulacion === null
      ? {}
      : { watermark: { text: nota.anulacion.marca, color: '#dc2626', opacity: 0.15, bold: true, fontSize: 110 } }),
    content: [
      encabezado(nota),
      bloqueDeCliente(nota),
      ...bloqueDeAnulacion(nota),
      tablaDeLineas(nota),
      tablaDeTotales(nota),
      bloqueDeCobranza(nota),
      ...bloqueDeSaldo(nota),
    ],
    footer: { text: nota.leyenda, alignment: 'center', fontSize: 9, color: '#6b7280', margin: [0, 20, 0, 0] },
  }
}
