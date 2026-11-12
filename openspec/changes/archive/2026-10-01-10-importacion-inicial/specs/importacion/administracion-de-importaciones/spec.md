## Purpose

Ofrecer en el área `/admin` una pantalla para elegir el tipo de importación, descargar su plantilla, subir el archivo, ver el resultado o el informe de errores por fila y consultar el historial, mostrando solo lo que el usuario puede hacer.

## ADDED Requirements

### Requirement: Pantalla de importación

El área `/admin` DEBE ofrecer una pantalla de importación visible solo con `IMPORTAR_DATOS` (ADR-027), que permita elegir el tipo, descargar la plantilla del tipo, seleccionar un archivo CSV o `.xlsx` e importarlo. La pantalla NO DEBE leer ni validar el contenido del archivo por su cuenta: el servidor valida todo (TR-10).

#### Scenario: Menú sin permiso

- **GIVEN** un Vendedor sin `IMPORTAR_DATOS`
- **WHEN** entra a `/admin`
- **THEN** no ve la entrada de importación y la ruta directa le muestra que no tiene permiso
- **Regla:** ADR-027; SEG-06

#### Scenario: Importación exitosa

- **GIVEN** un Administrador en la pantalla de importación
- **WHEN** elige "Proveedores", selecciona una planilla válida de dos filas e importa
- **THEN** ve "2 filas importadas" y la importación aparece en el historial
- **Regla:** `design.md` D1

### Requirement: Informe de errores en pantalla

Cuando el servidor rechaza la importación, la pantalla DEBE mostrar todos los errores en una tabla con fila, columna, código y mensaje, y el error de archivo (`ARCHIVO_INVALIDO`, `COLUMNAS_INVALIDAS`, etc.) como mensaje general. DEBE dejar claro que no se importó ninguna fila.

#### Scenario: Errores por fila

- **GIVEN** una planilla de clientes con errores en las filas 45 y 210
- **WHEN** se importa
- **THEN** la pantalla muestra una tabla con esas dos filas, sus columnas y códigos, y el aviso "No se importó ninguna fila"
- **Regla:** INV-01

#### Scenario: Error de columnas

- **GIVEN** una planilla de productos sin la columna `codigo`
- **WHEN** se importa
- **THEN** la pantalla muestra el mensaje de columnas inválidas nombrando `codigo`
- **Regla:** `design.md` D11

### Requirement: Reintento seguro

La pantalla DEBE generar un `Operation-Id` (UUIDv7) por cada archivo seleccionado y reutilizarlo si el usuario reintenta tras un error de red, y DEBE generar uno nuevo al seleccionar otro archivo o el mismo corregido (SYN-02).

#### Scenario: Reintento tras corte de red

- **GIVEN** una importación enviada cuya respuesta se perdió por un corte de red
- **WHEN** el usuario pulsa "Reintentar" sin cambiar el archivo
- **THEN** la pantalla reenvía con el mismo `Operation-Id` y muestra el resultado original, sin duplicar
- **Regla:** INV-06; SYN-02

### Requirement: Historial en pantalla

La pantalla DEBE listar el historial de importaciones (tipo, archivo, filas importadas, usuario, fecha en la zona horaria de la organización), con paginación.

#### Scenario: Ver historial

- **GIVEN** dos importaciones previas
- **WHEN** el Administrador abre la pantalla
- **THEN** ve ambas con su tipo, archivo y fecha en la zona de la organización
- **Regla:** TR-04
