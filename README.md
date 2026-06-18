# anthology-sis

Python client for the **Anthology Student** (CampusNexus) Query API — an OData v4
service under `…/ds/odata/`. Provides typed paging, Application-Key auth, and a CLI
for querying terms and class sections.

## Install

```bash
git clone <your-repo-url> anthology-sis
cd anthology-sis
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
# edit .env and paste your Application Key into CNX_API_KEY
```

The key is sent as `Authorization: ApplicationKey <key>`. `.env` is gitignored.

## Use

```bash
# Terms (order-independent search; names are year-first like "2026 Fall")
anthology-sis terms --search "fall 2026"

# Sections for a term -> CSV (deduped on ClassSectionId, follows paging)
anthology-sis sections --term-code 2025-FA-HS
anthology-sis sections --term-prefix 2025-FA --out fall25-family.csv
anthology-sis sections --term-id 904

# A single section, with related entities resolved
anthology-sis section --id 113884 --expand Course,Campus,Instructor,Terms

# A course, by id / exact code / title (title search is case-insensitive
# and order-independent: "art history" matches "Introduction To Art History")
anthology-sis course --id 131
anthology-sis course --code ART155
anthology-sis course --title "art history"

# Roster: students registered in a section (by ClassSection Id)
anthology-sis roster --section-id 856
anthology-sis roster --section-id 856 --out roster.csv

# Student lookup (by id / email / username): course history + financial ledger
anthology-sis student --id 787
anthology-sis student --email jdoe@example.edu
anthology-sis student --username jdoe                    # = email local-part
anthology-sis student --id 787 --term-code 2023-FA-HS-YR   # scope both to one term
anthology-sis student --id 6475 --out-prefix charles
```

### Student lookup (`student`)

Looks up one student **by `--id`, `--email`, or `--username`** (username = the email
local-part, since there is no stored username field) and prints two sections:

- **Course history** — every `StudentCourse` for the student (`Course`/`Term` expanded):
  term, course code/title, `Status`, `LetterGrade`, and `AddedOn`.
- **Ledger** — the student's `StudentAccountTransactions`: date, code, description, and a
  signed `Amount` (charges positive, waivers/credits negative), ending with the account
  `Balance` (the signed sum).

`--term-code CODE` scopes **both** sections to one term (resolved to a `TermId` that
filters the course history and the ledger). `--out-prefix NAME` writes
`NAME-courses.csv` and `NAME-ledger.csv`.

### Roster (`roster`)

Lists the students registered in a `ClassSection`, pulled from the `StudentCourses`
collection filtered by `ClassSectionId` (with the `Student` expanded for the name):
`StudentName`, `StudentId`, `StudentNumber`, `StudentEmail`, `StudentUsername`,
`Status`, `AddedOn` (when added to the section), and `LetterGrade`/`NumericGrade`.
`Status` is a free-text code — observed values: `P` (registered/active), `D`
(dropped — carries a `DropDate`), `F` (failed). There is no stored student username
field, so `StudentUsername` is derived from the email local-part (`EmailAddress`).

### What the `sections` CSV contains

Each row is one section (deduped on `ClassSectionId`) enriched via nested `$expand`:

- **Section:** `SectionStartDate` / `SectionEndDate` (the section's own run dates,
  not the term's), plus `IsActive`, `IsCancelled`, `MaximumStudents`,
  `NumberRegisteredStudents`, and a derived `SeatsOpen` (capacity − registered).
- **Location / modality** (resolved lookup entities): `CampusCode`/`CampusName` and
  `DeliveryMethodCode`/`DeliveryMethod` (e.g. `F2F` Face to Face, `HSC` High School).
  These are clean Id/Code/Name lookups — unlike the free-text `Note` location label.
- **Course** (via the `Course` nav property): `CourseName`, `CourseCreditHours`,
  `CourseClockHours`, `CourseDescription`. Note the `Course` entity has **no
  separate Title/Description** field — `Name` is the title and `Note` is the
  catalog description.
- **Instructor** (via `Instructor → Staff → Person`): `InstructorName`,
  `InstructorEmail`, `InstructorPhone`, `InstructorUsername`, `InstructorId`,
  `InstructorStaffId`, `InstructorDob`.

A `ClassSection` has **no single status field**: active/inactive is `IsActive`,
cancelled is `IsCancelled`, and "open" is derived from the seat counts (`SeatsOpen`).

## As a library

```python
from anthology_sis import load_config, ODataClient
from anthology_sis import queries as q

client = ODataClient(load_config())
rows = client.iter_collection(
    "ds/odata/ClassSectionTerms",
    select="ClassSectionId,TermId,TermCode,TermName",
    filter_=q.section_term_filter(code="2025-FA-HS"),
    expand=q.section_expand(),
)
sections, per_term = q.flatten_section_rows(rows)
```

## Test

```bash
pytest
```

See `CLAUDE.md` for the data-model notes (the term→section join entity, the sub-term
family pattern, and other gotchas reverse-engineered from `$metadata`).
