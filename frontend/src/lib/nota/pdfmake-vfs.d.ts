/** `pdfmake/build/vfs_fonts` no trae tipos: es el diccionario archivo -> fuente en base64 (Roboto). */
declare module 'pdfmake/build/vfs_fonts' {
  const vfs: Record<string, string>
  export default vfs
}
