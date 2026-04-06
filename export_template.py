"""Query SF foundation objects and generate Basic Import template."""
import asyncio
import httpx
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.sf_client import SFClient

OUTPUT = r"C:\Users\JoséMachado\Desktop\SF_Basic_Import_5Empleados.xlsx"


async def main():
    api_host = resolve_api_host()
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http)
        sf = SFClient(http)

        # Query foundation objects for reference
        fo_data = {}
        queries = {
            "FOCompany": "externalCode,name,country",
            "FODepartment": "externalCode,name",
            "FOJobCode": "externalCode,name,grade",
            "FOLocation": "externalCode,name",
            "FOPayGrade": "externalCode,name",
            "FOBusinessUnit": "externalCode,name",
            "FODivision": "externalCode,name",
            "FOEventReason": "externalCode,name",
        }
        for entity, fields in queries.items():
            try:
                result = await sf.query_odata(
                    data_center=api_host,
                    bearer_token=token,
                    entity=entity,
                    params={"$select": fields, "$top": "50"},
                )
                records = result.get("d", {}).get("results", [])
                fo_data[entity] = records
                print(f"{entity}: {len(records)} records")
            except Exception as e:
                fo_data[entity] = []
                print(f"{entity}: Error - {str(e)[:80]}")

    # Print reference data
    for entity, records in fo_data.items():
        if records:
            print(f"\n=== {entity} ===")
            for r in records[:20]:
                code = r.get("externalCode", "")
                name = r.get("name", "")
                extra = r.get("country", r.get("grade", ""))
                print(f"  {code:15s} {name:35s} {extra}")

    # --- Build Excel template ---
    wb = Workbook()

    # Sheet 1: Import Template
    ws = wb.active
    ws.title = "Basic Import"

    # SF Basic Import headers
    headers = [
        "personIdExternal",
        "firstName",
        "lastName",
        "gender",
        "dateOfBirth",
        "userId",
        "hireDate",
        "company",
        "department",
        "jobCode",
        "location",
        "countryOfCompany",
        "employeeClass",
        "payGrade",
        "division",
        "businessUnit",
        "eventReason",
        "email",
        "customString1",
    ]

    # Styles
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1A5276", end_color="1A5276", fill_type="solid")
    data_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    # Write headers
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    # Get valid codes from foundation objects
    companies = [r["externalCode"] for r in fo_data.get("FOCompany", [])]
    departments = [r["externalCode"] for r in fo_data.get("FODepartment", [])]
    job_codes = [r["externalCode"] for r in fo_data.get("FOJobCode", [])]
    locations = [r["externalCode"] for r in fo_data.get("FOLocation", [])]
    pay_grades = [r["externalCode"] for r in fo_data.get("FOPayGrade", [])]
    divisions = [r["externalCode"] for r in fo_data.get("FODivision", [])]
    bus_units = [r["externalCode"] for r in fo_data.get("FOBusinessUnit", [])]
    event_reasons = [r["externalCode"] for r in fo_data.get("FOEventReason", [])]

    # Find a HIRNEW event reason
    hire_reason = "HIRNEW"
    for r in fo_data.get("FOEventReason", []):
        code = r.get("externalCode", "")
        name = r.get("name", "").lower()
        if "hire" in name or "new" in name or code == "HIRNEW":
            hire_reason = code
            break

    # 5 dummy employees using REAL codes from your instance
    employees = [
        {
            "personIdExternal": "EMP001",
            "firstName": "Carlos",
            "lastName": "Mendoza",
            "gender": "M",
            "dateOfBirth": "1990-05-15",
            "userId": "cmendoza",
            "hireDate": "2026-03-10",
            "company": "PE01",
            "department": "40000013",
            "jobCode": "70000011" if "70000011" in job_codes else job_codes[0] if job_codes else "",
            "location": locations[0] if locations else "",
            "countryOfCompany": "PER",
            "employeeClass": "",
            "payGrade": "GR-3" if "GR-3" in pay_grades else pay_grades[0] if pay_grades else "",
            "division": divisions[0] if divisions else "",
            "businessUnit": bus_units[0] if bus_units else "",
            "eventReason": hire_reason,
            "email": "carlos.mendoza@vpmc.com",
            "customString1": "",
        },
        {
            "personIdExternal": "EMP002",
            "firstName": "Maria",
            "lastName": "Rodriguez",
            "gender": "F",
            "dateOfBirth": "1988-11-22",
            "userId": "mrodriguez",
            "hireDate": "2026-03-10",
            "company": "1710",
            "department": "40000002",
            "jobCode": "70000012" if "70000012" in job_codes else job_codes[1] if len(job_codes) > 1 else "",
            "location": locations[1] if len(locations) > 1 else locations[0] if locations else "",
            "countryOfCompany": "USA",
            "employeeClass": "",
            "payGrade": "GR-4" if "GR-4" in pay_grades else "",
            "division": divisions[0] if divisions else "",
            "businessUnit": bus_units[0] if bus_units else "",
            "eventReason": hire_reason,
            "email": "maria.rodriguez@vpmc.com",
            "customString1": "",
        },
        {
            "personIdExternal": "EMP003",
            "firstName": "James",
            "lastName": "Thompson",
            "gender": "M",
            "dateOfBirth": "1995-03-08",
            "userId": "jthompson",
            "hireDate": "2026-03-10",
            "company": "CA01",
            "department": "40000018",
            "jobCode": "70000015" if "70000015" in job_codes else job_codes[2] if len(job_codes) > 2 else "",
            "location": locations[2] if len(locations) > 2 else locations[0] if locations else "",
            "countryOfCompany": "CAN",
            "employeeClass": "",
            "payGrade": "GR-4" if "GR-4" in pay_grades else "",
            "division": divisions[0] if divisions else "",
            "businessUnit": bus_units[0] if bus_units else "",
            "eventReason": hire_reason,
            "email": "james.thompson@vpmc.com",
            "customString1": "",
        },
        {
            "personIdExternal": "EMP004",
            "firstName": "Lucia",
            "lastName": "Fernandez",
            "gender": "F",
            "dateOfBirth": "1992-07-30",
            "userId": "lfernandez",
            "hireDate": "2026-03-10",
            "company": "MX01",
            "department": "40000019",
            "jobCode": "70000021" if "70000021" in job_codes else job_codes[3] if len(job_codes) > 3 else "",
            "location": locations[3] if len(locations) > 3 else locations[0] if locations else "",
            "countryOfCompany": "MEX",
            "employeeClass": "",
            "payGrade": "GR-1" if "GR-1" in pay_grades else "",
            "division": divisions[0] if divisions else "",
            "businessUnit": bus_units[0] if bus_units else "",
            "eventReason": hire_reason,
            "email": "lucia.fernandez@vpmc.com",
            "customString1": "",
        },
        {
            "personIdExternal": "EMP005",
            "firstName": "Andres",
            "lastName": "Vargas",
            "gender": "M",
            "dateOfBirth": "1993-12-01",
            "userId": "avargas",
            "hireDate": "2026-03-10",
            "company": "CL01",
            "department": "40000020",
            "jobCode": "70000010" if "70000010" in job_codes else job_codes[4] if len(job_codes) > 4 else "",
            "location": locations[4] if len(locations) > 4 else locations[0] if locations else "",
            "countryOfCompany": "CHL",
            "employeeClass": "",
            "payGrade": "GR-2" if "GR-2" in pay_grades else "",
            "division": divisions[0] if divisions else "",
            "businessUnit": bus_units[0] if bus_units else "",
            "eventReason": hire_reason,
            "email": "andres.vargas@vpmc.com",
            "customString1": "",
        },
    ]

    # Write data rows
    for row_idx, emp in enumerate(employees, 2):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=row_idx, column=col, value=emp.get(h, ""))
            cell.font = data_font
            cell.border = thin_border

    # Column widths
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 18

    ws.freeze_panes = "A2"

    # Sheet 2: Reference data
    ws2 = wb.create_sheet("Referencia FO")
    ws2_row = 1
    ref_fill = PatternFill(start_color="2E86C1", end_color="2E86C1", fill_type="solid")
    ref_font = Font(name="Calibri", bold=True, color="FFFFFF", size=10)

    for entity, records in fo_data.items():
        if not records:
            continue
        cell = ws2.cell(row=ws2_row, column=1, value=entity)
        cell.font = ref_font
        cell.fill = ref_fill
        cell2 = ws2.cell(row=ws2_row, column=2, value="Code")
        cell2.font = ref_font
        cell2.fill = ref_fill
        cell3 = ws2.cell(row=ws2_row, column=3, value="Name")
        cell3.font = ref_font
        cell3.fill = ref_fill
        cell4 = ws2.cell(row=ws2_row, column=4, value="Extra")
        cell4.font = ref_font
        cell4.fill = ref_fill
        ws2_row += 1

        for r in records[:25]:
            ws2.cell(row=ws2_row, column=1, value=entity).font = data_font
            ws2.cell(row=ws2_row, column=2, value=r.get("externalCode", "")).font = data_font
            ws2.cell(row=ws2_row, column=3, value=r.get("name", "")).font = data_font
            ws2.cell(row=ws2_row, column=4, value=r.get("country", r.get("grade", ""))).font = data_font
            ws2_row += 1
        ws2_row += 1

    ws2.column_dimensions["A"].width = 18
    ws2.column_dimensions["B"].width = 18
    ws2.column_dimensions["C"].width = 40
    ws2.column_dimensions["D"].width = 15

    wb.save(OUTPUT)
    print(f"\n{'='*50}")
    print(f"Excel generado: {OUTPUT}")
    print(f"5 empleados con datos reales de tu instancia")
    print(f"{'='*50}")


asyncio.run(main())
