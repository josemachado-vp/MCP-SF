"""Generate Basic Import CSV matching the exact VPMCSandbox template format."""
import csv

OUTPUT = r"C:\Users\JoséMachado\Desktop\SF_Basic_Import_5Empleados.csv"

# Row 1: Field API names (exact match from your template)
header_row = [
    "STATUS", "USERID", "USERNAME", "FIRSTNAME", "NICKNAME", "MI", "LASTNAME",
    "GENDER", "EMAIL", "MANAGER", "HR", "DEPARTMENT", "JOBCODE", "DIVISION",
    "LOCATION", "TIMEZONE", "HIREDATE", "EMPID", "TITLE", "BIZ_PHONE", "FAX",
    "ADDR1", "ADDR2", "CITY", "STATE", "ZIP", "COUNTRY", "DEFAULT_LOCALE",
    "REVIEW_FREQ", "LAST_REVIEW_DATE", "CUSTOM01", "CUSTOM02", "CUSTOM03",
    "CUSTOM04", "CUSTOM05", "CUSTOM06", "CUSTOM07", "CUSTOM08", "CUSTOM09",
    "CUSTOM10", "CUSTOM11", "CUSTOM12", "CUSTOM13", "CUSTOM14", "CUSTOM15",
    "MATRIX_MANAGER", "PROXY", "CUSTOM_MANAGER", "SECOND_MANAGER",
    "LOGIN_METHOD", "COMPANYEXITDATE", "ASSIGNMENTUUID", "DISPLAYNAME",
    "PERSON_ID_EXTERNAL",
]

# Row 2: Human-readable labels (exact match from your template)
label_row = [
    "STATUS", "USERID", "Username", "First Name", "Nickname", "Middle Name",
    "Last Name", "Gender", "Email", "Manager", "Human Resource", "Department",
    "Job Code", "Division", "Location", "Time Zone", "Hire Date", "Employee Id",
    "Business Title", "Business Phone", "Business Fax", "Address 1", "Address 2",
    "City", "State", "ZIP", "Country", "Default Locale", "Review Frequency",
    "Last Review Date", "Legal Entity", "Business Unit", "Second Last Name",
    "Is Manager", "Customizable Field 5", "Customizable Field 6",
    "Customizable Field 7", "Customizable Field 8", "Customizable Field 9",
    "Customizable Field 10", "Customizable Field 11", "Customizable Field 12",
    "Customizable Field 13", "Customizable Field 14", "Customizable Field 15",
    "Matrix Manager", "Proxy", "Custom Manager", "Second Manager",
    "Login Method", "Termination Date", "Assignment UUID", "Display Name",
    "PERSON_ID_EXTERNAL",
]


def make_emp(
    pid, uid, first, last, gender, email, dept, jobcode, division,
    location, tz, country, locale, legal_entity, bus_unit, title,
    addr1="", city="", state="", zipcode="", nickname="", mi="",
):
    """Build a dict for one employee row."""
    emp = {h: "" for h in header_row}
    emp.update({
        "STATUS": "NEW",
        "USERID": uid,
        "USERNAME": uid,
        "FIRSTNAME": first,
        "NICKNAME": nickname,
        "MI": mi,
        "LASTNAME": last,
        "GENDER": gender,
        "EMAIL": email,
        "MANAGER": "adminJM",
        "HR": "adminJM",
        "DEPARTMENT": dept,
        "JOBCODE": jobcode,
        "DIVISION": division,
        "LOCATION": location,
        "TIMEZONE": tz,
        "HIREDATE": "03/10/2026",
        "EMPID": pid,
        "TITLE": title,
        "ADDR1": addr1,
        "CITY": city,
        "STATE": state,
        "ZIP": zipcode,
        "COUNTRY": country,
        "DEFAULT_LOCALE": locale,
        "CUSTOM01": legal_entity,    # Legal Entity
        "CUSTOM02": bus_unit,        # Business Unit
        "CUSTOM03": "",              # Second Last Name
        "CUSTOM04": "N",             # Is Manager
        "LOGIN_METHOD": "PWD",
        "DISPLAYNAME": f"{first} {last}",
        "PERSON_ID_EXTERNAL": pid,
    })
    return emp


# 5 dummy employees using REAL codes from VPMCSandbox
employees = [
    make_emp(
        pid="EMP001", uid="cmendoza",
        first="Carlos", last="Mendoza", gender="M",
        email="carlos.mendoza@vpmc.com",
        dept="40000013",           # Perú Dep
        jobcode="70000011",        # HR Analyst
        division="30000012",       # Peru Div
        location="PE01_1001",      # Lima - Oficina Central
        tz="America/Lima",
        country="PER", locale="es_ES",
        legal_entity="PE01", bus_unit="20000006",  # Operations
        title="HR Analyst",
        addr1="Av. Javier Prado 123", city="Lima", zipcode="15036",
    ),
    make_emp(
        pid="EMP002", uid="mrodriguez",
        first="Maria", last="Rodriguez", gender="F", mi="A",
        email="maria.rodriguez@vpmc.com",
        dept="40000002",           # Human Resources
        jobcode="70000012",        # HR Business Partner
        division="30000014",       # Global HR
        location="1710-2015",      # Atlanta
        tz="US/Eastern",
        country="USA", locale="en_US",
        legal_entity="1710", bus_unit="20000005",  # Human Resources
        title="HR Business Partner",
        addr1="100 Peachtree St", city="Atlanta", state="GA", zipcode="30303",
    ),
    make_emp(
        pid="EMP003", uid="jthompson",
        first="James", last="Thompson", gender="M", nickname="Jim",
        email="james.thompson@vpmc.com",
        dept="40000018",           # Canada Department
        jobcode="70000015",        # IT Analyst
        division="30000021",       # Canada Division
        location="CA01_1009",      # Alberta
        tz="Canada/Mountain",
        country="CAN", locale="en_US",
        legal_entity="CA01", bus_unit="20000008",  # IT
        title="IT Analyst",
        addr1="456 Maple Avenue", city="Calgary", state="AB", zipcode="T2P 1J9",
    ),
    make_emp(
        pid="EMP004", uid="lfernandez",
        first="Lucia", last="Fernandez", gender="F",
        email="lucia.fernandez@vpmc.com",
        dept="40000019",           # Mexico Department
        jobcode="70000021",        # Logistics Operative
        division="30000022",       # Mexico Division
        location="MX01_1001",      # Ciudad de Mexico
        tz="America/Mexico_City",
        country="MEX", locale="es_MX",
        legal_entity="MX01", bus_unit="20000006",  # Operations
        title="Logistics Operative",
        addr1="Paseo de la Reforma 505", city="Ciudad de Mexico",
        state="CDMX", zipcode="06500",
    ),
    make_emp(
        pid="EMP005", uid="avargas",
        first="Andres", last="Vargas", gender="M",
        email="andres.vargas@vpmc.com",
        dept="40000020",           # Industrial Operations
        jobcode="70000010",        # HR Administrator
        division="30000024",       # Chile Operations
        location="CL01_1001",      # Santiago
        tz="America/Santiago",
        country="CHL", locale="es_ES",
        legal_entity="CL01", bus_unit="20000006",  # Operations
        title="HR Administrator",
        addr1="Av. Providencia 1234", city="Santiago", state="RM",
        zipcode="7500000",
    ),
]


# Write CSV
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
    writer.writerow(header_row)
    writer.writerow(label_row)
    for emp in employees:
        row = [emp.get(h, "") for h in header_row]
        writer.writerow(row)

print(f"CSV generado: {OUTPUT}")
print(f"Empleados: {len(employees)}")
print(f"Columnas: {len(header_row)}")
print()
for emp in employees:
    print(f"  {emp['PERSON_ID_EXTERNAL']:8s} {emp['FIRSTNAME']:10s} {emp['LASTNAME']:12s} | {emp['CUSTOM01']:5s} {emp['DEPARTMENT']:10s} {emp['JOBCODE']:10s} {emp['COUNTRY']}")
