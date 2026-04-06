const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat,
} = require("docx");

const SAP_BLUE = "0070F2";
const SAP_DARK = "1B2559";
const SAP_LIGHT = "EBF5FF";
const GRAY_BG = "F5F5F5";
const WHITE = "FFFFFF";

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: SAP_BLUE, type: ShadingType.CLEAR },
    margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text, bold: true, color: WHITE, font: "Arial", size: 20 })] })],
  });
}

function dataCell(text, width, opts = {}) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: opts.shading ? { fill: opts.shading, type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: [new Paragraph({
      alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ text: text || "", font: "Arial", size: 20, bold: opts.bold || false, color: opts.color || "333333" })],
    })],
  });
}

function labelValueRow(label, value, labelW, valueW) {
  return new TableRow({
    children: [
      new TableCell({
        borders, width: { size: labelW, type: WidthType.DXA },
        shading: { fill: GRAY_BG, type: ShadingType.CLEAR }, margins: cellMargins,
        children: [new Paragraph({ children: [new TextRun({ text: label, bold: true, font: "Arial", size: 20, color: SAP_DARK })] })],
      }),
      new TableCell({
        borders, width: { size: valueW, type: WidthType.DXA }, margins: cellMargins,
        children: [new Paragraph({ children: [new TextRun({ text: value, font: "Arial", size: 20 })] })],
      }),
    ],
  });
}

// --- Build Document ---
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: SAP_DARK },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: SAP_BLUE },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "444444" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "substeps", levels: [{ level: 0, format: LevelFormat.LOWER_LETTER, text: "%1)", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 360 } } } }] },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1200, bottom: 1440, left: 1200 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: SAP_BLUE, space: 1 } },
            spacing: { after: 120 },
            children: [
              new TextRun({ text: "SAP SuccessFactors", bold: true, font: "Arial", size: 18, color: SAP_BLUE }),
              new TextRun({ text: "  |  Business Rule Documentation  |  VPMCSandbox", font: "Arial", size: 16, color: "888888" }),
            ],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 2, color: "CCCCCC", space: 1 } },
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "Generado por MCP SF Business Rules  |  ", font: "Arial", size: 16, color: "999999" }),
              new TextRun({ text: "Pagina ", font: "Arial", size: 16, color: "999999" }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" }),
            ],
          })],
        }),
      },
      children: [
        // ===== TITLE =====
        new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: "Business Rule", font: "Arial", size: 44, bold: true, color: SAP_DARK })] }),
        new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Derivar Country Code de Telefono desde Pais", font: "Arial", size: 32, color: SAP_BLUE })] }),
        new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "(Local Information)", font: "Arial", size: 28, color: "666666" })] }),
        new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: SAP_BLUE, space: 1 } }, spacing: { after: 300 }, children: [] }),

        // ===== SECTION 1: RESUMEN =====
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("1. Resumen de la Regla")] }),
        new Table({
          width: { size: 9840, type: WidthType.DXA },
          columnWidths: [3200, 6640],
          rows: [
            labelValueRow("Rule Name", "BR_Derive_PhoneCountryCode_From_Country", 3200, 6640),
            labelValueRow("Scenario", "Rules for Employee Central", 3200, 6640),
            labelValueRow("Base Object", "PersonalInfoModel", 3200, 6640),
            labelValueRow("Event Type", "onChange", 3200, 6640),
            labelValueRow("HRIS Element", "Phone Information", 3200, 6640),
            labelValueRow("Trigger Field", "Country/Region (Local Information)", 3200, 6640),
            labelValueRow("Target Field", "Country Code (Phone Information)", 3200, 6640),
          ],
        }),
        new Paragraph({ spacing: { before: 200, after: 200 }, children: [
          new TextRun({ text: "Descripcion: ", bold: true, font: "Arial", size: 22 }),
          new TextRun({ text: "Cuando el usuario selecciona o cambia el Country/Region en la seccion Local Information, el Country Code en Phone Information se llena automaticamente con el codigo telefonico del pais correspondiente.", font: "Arial", size: 22 }),
        ] }),

        // ===== SECTION 2: MAPEO =====
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("2. Mapeo de Pais a Country Code")] }),
        new Table({
          width: { size: 9840, type: WidthType.DXA },
          columnWidths: [3280, 3280, 3280],
          rows: [
            new TableRow({ children: [headerCell("Pais", 3280), headerCell("Codigo ISO", 3280), headerCell("Country Code", 3280)] }),
            new TableRow({ children: [dataCell("Peru", 3280), dataCell("PER", 3280, { center: true }), dataCell("+51", 3280, { center: true, bold: true, color: SAP_BLUE })] }),
            new TableRow({ children: [dataCell("Estados Unidos", 3280, { shading: GRAY_BG }), dataCell("USA", 3280, { center: true, shading: GRAY_BG }), dataCell("+1", 3280, { center: true, bold: true, color: SAP_BLUE, shading: GRAY_BG })] }),
            new TableRow({ children: [dataCell("Canada", 3280), dataCell("CAN", 3280, { center: true }), dataCell("+1", 3280, { center: true, bold: true, color: SAP_BLUE })] }),
            new TableRow({ children: [dataCell("Mexico", 3280, { shading: GRAY_BG }), dataCell("MEX", 3280, { center: true, shading: GRAY_BG }), dataCell("+52", 3280, { center: true, bold: true, color: SAP_BLUE, shading: GRAY_BG })] }),
            new TableRow({ children: [dataCell("Chile", 3280), dataCell("CHL", 3280, { center: true }), dataCell("+56", 3280, { center: true, bold: true, color: SAP_BLUE })] }),
            new TableRow({ children: [dataCell("Jamaica", 3280, { shading: GRAY_BG }), dataCell("JAM", 3280, { center: true, shading: GRAY_BG }), dataCell("+1876", 3280, { center: true, bold: true, color: SAP_BLUE, shading: GRAY_BG })] }),
          ],
        }),

        // ===== SECTION 3: IMPLEMENTACION =====
        new Paragraph({ children: [new PageBreak()] }),
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("3. Pasos de Implementacion")] }),

        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 80 }, children: [
          new TextRun({ text: "Iniciar sesion en SAP SuccessFactors como Administrador", font: "Arial", size: 22 }),
        ] }),
        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 80 }, children: [
          new TextRun({ text: "Navegar a ", font: "Arial", size: 22 }),
          new TextRun({ text: "Admin Center", bold: true, font: "Arial", size: 22 }),
          new TextRun({ text: " y buscar ", font: "Arial", size: 22 }),
          new TextRun({ text: "\"Configure Business Rules\"", bold: true, color: SAP_BLUE, font: "Arial", size: 22 }),
        ] }),
        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 80 }, children: [
          new TextRun({ text: "Click en ", font: "Arial", size: 22 }),
          new TextRun({ text: "\"+\" (Crear Nueva Regla)", bold: true, font: "Arial", size: 22 }),
        ] }),
        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 80 }, children: [
          new TextRun({ text: "En el dialogo de creacion configurar:", font: "Arial", size: 22 }),
        ] }),

        new Table({
          width: { size: 8400, type: WidthType.DXA },
          columnWidths: [3000, 5400],
          indent: { size: 720, type: WidthType.DXA },
          rows: [
            labelValueRow("Rule Name", "BR_Derive_PhoneCountryCode_From_Country", 3000, 5400),
            labelValueRow("Scenario", "Rules for Employee Central", 3000, 5400),
            labelValueRow("Base Object", "PersonalInfoModel (Personal Info)", 3000, 5400),
          ],
        }),
        new Paragraph({ spacing: { before: 80, after: 80 }, indent: { left: 720 }, children: [
          new TextRun({ text: "Click ", font: "Arial", size: 22 }),
          new TextRun({ text: "\"Continue\"", bold: true, color: SAP_BLUE, font: "Arial", size: 22 }),
        ] }),

        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { before: 200, after: 120 }, children: [
          new TextRun({ text: "Configurar las condiciones IF / ELSE IF:", bold: true, font: "Arial", size: 22 }),
        ] }),

        // Condition 1
        new Paragraph({ heading: HeadingLevel.HEADING_3, indent: { left: 720 }, children: [new TextRun("Condicion 1 (IF) - Peru")] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "IF ", bold: true, color: "CC0000", font: "Arial", size: 20 }),
          new TextRun({ text: "PersonalInfoModel.phone_information.country_code.", font: "Consolas", size: 18 }),
          new TextRun({ text: "country", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "Peru", bold: true, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 160 }, children: [
          new TextRun({ text: "THEN Set ", bold: true, color: "008000", font: "Arial", size: 20 }),
          new TextRun({ text: "phone_information.", font: "Consolas", size: 18 }),
          new TextRun({ text: "country_code", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "\"+51\"", bold: true, font: "Arial", size: 20, color: SAP_BLUE }),
        ] }),

        // Condition 2
        new Paragraph({ heading: HeadingLevel.HEADING_3, indent: { left: 720 }, children: [new TextRun("Condicion 2 (ELSE IF) - Estados Unidos")] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "ELSE IF ", bold: true, color: "CC0000", font: "Arial", size: 20 }),
          new TextRun({ text: "country", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "United States", bold: true, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 160 }, children: [
          new TextRun({ text: "THEN Set ", bold: true, color: "008000", font: "Arial", size: 20 }),
          new TextRun({ text: "country_code", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "\"+1\"", bold: true, font: "Arial", size: 20, color: SAP_BLUE }),
        ] }),

        // Condition 3
        new Paragraph({ heading: HeadingLevel.HEADING_3, indent: { left: 720 }, children: [new TextRun("Condicion 3 (ELSE IF) - Canada")] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "ELSE IF ", bold: true, color: "CC0000", font: "Arial", size: 20 }),
          new TextRun({ text: "country", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "Canada", bold: true, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 160 }, children: [
          new TextRun({ text: "THEN Set ", bold: true, color: "008000", font: "Arial", size: 20 }),
          new TextRun({ text: "country_code", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "\"+1\"", bold: true, font: "Arial", size: 20, color: SAP_BLUE }),
        ] }),

        // Condition 4
        new Paragraph({ heading: HeadingLevel.HEADING_3, indent: { left: 720 }, children: [new TextRun("Condicion 4 (ELSE IF) - Mexico")] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "ELSE IF ", bold: true, color: "CC0000", font: "Arial", size: 20 }),
          new TextRun({ text: "country", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "Mexico", bold: true, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 160 }, children: [
          new TextRun({ text: "THEN Set ", bold: true, color: "008000", font: "Arial", size: 20 }),
          new TextRun({ text: "country_code", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "\"+52\"", bold: true, font: "Arial", size: 20, color: SAP_BLUE }),
        ] }),

        // Condition 5
        new Paragraph({ heading: HeadingLevel.HEADING_3, indent: { left: 720 }, children: [new TextRun("Condicion 5 (ELSE IF) - Chile")] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "ELSE IF ", bold: true, color: "CC0000", font: "Arial", size: 20 }),
          new TextRun({ text: "country", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "Chile", bold: true, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 160 }, children: [
          new TextRun({ text: "THEN Set ", bold: true, color: "008000", font: "Arial", size: 20 }),
          new TextRun({ text: "country_code", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "\"+56\"", bold: true, font: "Arial", size: 20, color: SAP_BLUE }),
        ] }),

        // Condition 6
        new Paragraph({ heading: HeadingLevel.HEADING_3, indent: { left: 720 }, children: [new TextRun("Condicion 6 (ELSE IF) - Jamaica")] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "ELSE IF ", bold: true, color: "CC0000", font: "Arial", size: 20 }),
          new TextRun({ text: "country", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "Jamaica", bold: true, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ indent: { left: 1080 }, spacing: { after: 160 }, children: [
          new TextRun({ text: "THEN Set ", bold: true, color: "008000", font: "Arial", size: 20 }),
          new TextRun({ text: "country_code", bold: true, font: "Consolas", size: 18, color: SAP_BLUE }),
          new TextRun({ text: " = ", font: "Arial", size: 20 }),
          new TextRun({ text: "\"+1876\"", bold: true, font: "Arial", size: 20, color: SAP_BLUE }),
        ] }),

        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { before: 200, after: 80 }, children: [
          new TextRun({ text: "Click ", font: "Arial", size: 22 }),
          new TextRun({ text: "\"Save\"", bold: true, color: SAP_BLUE, font: "Arial", size: 22 }),
          new TextRun({ text: " para guardar la regla", font: "Arial", size: 22 }),
        ] }),

        new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 80 }, children: [
          new TextRun({ text: "Asignar la regla al evento onChange:", bold: true, font: "Arial", size: 22 }),
        ] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "En la seccion \"Event Type\" configurar: ", font: "Arial", size: 20 }),
          new TextRun({ text: "onChange", bold: true, color: SAP_BLUE, font: "Arial", size: 20 }),
        ] }),
        new Paragraph({ numbering: { reference: "bullets", level: 0 }, indent: { left: 1080 }, spacing: { after: 40 }, children: [
          new TextRun({ text: "Campo que dispara la regla: ", font: "Arial", size: 20 }),
          new TextRun({ text: "country (Local Information / Global Information)", bold: true, font: "Arial", size: 20 }),
        ] }),

        // ===== SECTION 4: TEST CASES =====
        new Paragraph({ children: [new PageBreak()] }),
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("4. Matriz de Test Cases")] }),
        new Table({
          width: { size: 9840, type: WidthType.DXA },
          columnWidths: [900, 2600, 2200, 2200, 1940],
          rows: [
            new TableRow({ children: [
              headerCell("TC#", 900), headerCell("Escenario", 2600),
              headerCell("Country/Region", 2200), headerCell("Expected Code", 2200),
              headerCell("Resultado", 1940),
            ] }),
            ...[
              ["TC001", "Pais Peru", "Peru (PER)", "+51"],
              ["TC002", "Pais USA", "United States (USA)", "+1"],
              ["TC003", "Pais Canada", "Canada (CAN)", "+1"],
              ["TC004", "Pais Mexico", "Mexico (MEX)", "+52"],
              ["TC005", "Pais Chile", "Chile (CHL)", "+56"],
              ["TC006", "Pais Jamaica", "Jamaica (JAM)", "+1876"],
              ["TC007", "Cambio PER a USA", "Peru -> USA", "+1 (actualiza)"],
              ["TC008", "Pais no mapeado", "Brazil (BRA)", "Sin cambio"],
              ["TC009", "Sin Local Info", "Sin pais", "Sin cambio"],
              ["TC010", "Nuevo empleado", "New Hire - Peru", "+51"],
            ].map((row, i) => {
              const bg = i % 2 === 1 ? GRAY_BG : undefined;
              return new TableRow({
                children: [
                  dataCell(row[0], 900, { center: true, bold: true, shading: bg }),
                  dataCell(row[1], 2600, { shading: bg }),
                  dataCell(row[2], 2200, { center: true, shading: bg }),
                  dataCell(row[3], 2200, { center: true, bold: true, color: SAP_BLUE, shading: bg }),
                  dataCell("\u2610 Pass", 1940, { center: true, shading: bg }),
                ],
              });
            }),
          ],
        }),

        // ===== SECTION 5: BEST PRACTICES =====
        new Paragraph({ spacing: { before: 400 }, heading: HeadingLevel.HEADING_1, children: [new TextRun("5. Notas y Mejores Practicas")] }),
        ...[
          "Esta regla se ejecuta en tiempo real (onChange) cuando el usuario modifica el campo Country/Region",
          "No afecta registros existentes - solo se aplica cuando hay un cambio activo en la UI",
          "Si se agrega un nuevo pais a la instancia, se debe actualizar esta regla con el nuevo codigo telefonico",
          "Evitar dependencias circulares con otras reglas que modifiquen Phone Information",
          "Probar con empleados de cada pais antes de transportar a produccion",
          "Documentar la regla en el registro de cambios del proyecto",
        ].map(text => new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          spacing: { after: 80 },
          children: [new TextRun({ text, font: "Arial", size: 22 })],
        })),

        // ===== SECTION 6: DOCUMENT INFO =====
        new Paragraph({ spacing: { before: 400 }, heading: HeadingLevel.HEADING_1, children: [new TextRun("6. Informacion del Documento")] }),
        new Table({
          width: { size: 6000, type: WidthType.DXA },
          columnWidths: [2400, 3600],
          rows: [
            labelValueRow("Instancia", "VPMCSandbox", 2400, 3600),
            labelValueRow("Autor", "Jose Machado", 2400, 3600),
            labelValueRow("Fecha", "10 de Marzo 2026", 2400, 3600),
            labelValueRow("Generado por", "MCP SF Business Rules", 2400, 3600),
          ],
        }),
      ],
    },
  ],
});

const OUTPUT = String.raw`C:\Users\JoséMachado\Desktop\BR_Derive_PhoneCountryCode.docx`;
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(OUTPUT, buffer);
  console.log(`Document created: ${OUTPUT}`);
  console.log(`Size: ${(buffer.length / 1024).toFixed(1)} KB`);
});
