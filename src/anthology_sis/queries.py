"""Pure query-building helpers — no network, fully unit-testable.

This is where the knowledge we reverse-engineered from the metadata lives:
- Terms search is order-independent (names are year-first, e.g. '2026 Fall').
- Sections attach to terms via the ClassSectionTerm join entity, which carries
  denormalized TermId/TermCode/TermName plus a ClassSection navigation property.
"""

from __future__ import annotations

from typing import Any, Iterable

# Trimmed section fields (the ClassSection entity has ~80 columns).
# StartDate/EndDate are the section's own run dates (distinct from the Term dates).
SECTION_SELECT = (
    "Id,CourseCode,SectionName,SectionCode,StartDate,EndDate,IsActive,IsCancelled,"
    "MaximumStudents,NumberRegisteredStudents,CampusId,CourseId,InstructorId"
)

# Course catalog detail, reached from a ClassSection via the Course nav property.
# Note: the Course entity has no separate Title/Description column — Name is the
# course title and Note holds the catalog description.
COURSE_SELECT = "Code,Name,CreditHours,ClockHours,Note"

# Fuller field set for querying the Courses collection directly (the `course` cmd).
COURSE_DETAIL_SELECT = (
    "Id,Code,CatalogCode,Name,CreditHours,ClockHours,UnitType,IsActive,Note"
)

# Roster: a section's registered students live in StudentCourse records (entity set
# StudentCourses), filtered by ClassSectionId, with the Student expanded for the name.
# Status is a free-text code (e.g. 'P', 'D', 'W'); CreatedDateTime is when the student
# was added to the section; the grade is LetterGrade/NumericGrade.
ROSTER_SELECT = "Id,StudentId,Status,CreatedDateTime,LetterGrade,NumericGrade"
ROSTER_STUDENT_SELECT = "Id,FullName,StudentNumber,EmailAddress"

ROSTER_CSV_FIELDS = [
    "StudentCourseId", "StudentId", "StudentNumber", "StudentName",
    "StudentUsername", "StudentEmail",
    "Status", "AddedOn", "LetterGrade", "NumericGrade",
]

# Student lookup (the `student` cmd). The student record is keyed by Id; their course
# history and financial ledger are separate collections filtered by StudentId.
STUDENT_SELECT = "Id,FullName,StudentNumber,FirstName,LastName,EmailAddress"

# Course history: StudentCourse rows for one student, with Course/Term expanded.
STUDENT_COURSE_SELECT = (
    "Id,ClassSectionId,CourseId,Status,LetterGrade,NumericGrade,CreatedDateTime"
)
STUDENT_COURSE_EXPAND = "Course($select=Code,Name),Term($select=Code,Name)"
STUDENT_COURSE_CSV_FIELDS = [
    "StudentCourseId", "TermCode", "CourseCode", "CourseName",
    "Status", "LetterGrade", "NumericGrade", "AddedOn",
]

# Ledger: StudentAccountTransaction rows. TransactionAmount is signed — positive is a
# charge (tuition/fees), negative a credit (waiver/payment); their sum is the balance.
LEDGER_SELECT = (
    "Id,TransactionDate,PostDate,Type,BillingTransactionCode,"
    "Description,TransactionAmount,AmountPaid"
)
LEDGER_CSV_FIELDS = [
    "TransactionId", "TransactionDate", "PostDate", "Type", "Code",
    "Description", "Amount", "AmountPaid",
]

# Instructor detail, reached from a ClassSection via Instructor -> Staff -> Person.
# The Instructor entity is thin (ids + display Name); the contact/identity fields
# live on the linked Staff record, and DateOfBirth on the linked Person.
INSTRUCTOR_SELECT = "InstructorId,StaffId"
INSTRUCTOR_STAFF_SELECT = "Id,Code,EmailAddress,FullName,PhoneNumber"
INSTRUCTOR_PERSON_SELECT = "DateOfBirth"

# Section location/modality lookups (clean Id/Code/Name entities, unlike free-text Note).
# DeliveryMethod 'HSC' = High School, the dual-enrollment indicator.
CAMPUS_SELECT = "Id,Code,Name"
DELIVERY_METHOD_SELECT = "Id,Code,Name"

# Output column order for flattened section CSV rows.
SECTION_CSV_FIELDS = [
    "ClassSectionId", "TermId", "TermCode", "TermName",
    "CourseCode", "SectionCode", "SectionName",
    "SectionStartDate", "SectionEndDate",
    "CourseName", "CourseCreditHours", "CourseClockHours", "CourseDescription",
    "IsActive", "IsCancelled",
    "MaximumStudents", "NumberRegisteredStudents", "SeatsOpen",
    "CampusId", "CampusCode", "CampusName",
    "DeliveryMethodCode", "DeliveryMethod",
    "CourseId",
    "InstructorId", "InstructorStaffId", "InstructorName", "InstructorEmail",
    "InstructorPhone", "InstructorUsername", "InstructorDob",
]


def odata_quote(value: str) -> str:
    """Escape single quotes for an OData string literal (double them)."""
    return value.replace("'", "''")


def term_search_filter(search: str) -> str:
    """Order-independent term-name match.

    'Fall 2026' -> "contains(Name,'Fall') and contains(Name,'2026')",
    which matches a record named '2026 Fall'.
    """
    words = [w for w in search.split() if w]
    clauses = [f"contains(Name,'{odata_quote(w)}')" for w in words]
    return " and ".join(clauses)


def course_filter(
    *, course_id: int | None = None, code: str | None = None,
    title: str | None = None,
) -> str:
    """Build the $filter for the Courses collection from one selector.

    - course_id -> "Id eq <n>"
    - code      -> exact "Code eq '<code>'" (case-sensitive, use real course codes)
    - title     -> order-independent, case-insensitive match on Name. contains()
      is case-sensitive on this provider, so both sides are lowered with tolower():
      'art history' -> "contains(tolower(Name),'art') and contains(tolower(Name),'history')".
    """
    if course_id is not None:
        return f"Id eq {course_id}"
    if code:
        return f"Code eq '{odata_quote(code)}'"
    if title:
        words = [w for w in title.lower().split() if w]
        if not words:
            raise ValueError("title has no searchable words.")
        clauses = [f"contains(tolower(Name),'{odata_quote(w)}')" for w in words]
        return " and ".join(clauses)
    raise ValueError("Provide one of: course_id, code, or title.")


def _email_localpart(email: Any) -> str | None:
    """The username portion of an email (before '@'), or None if absent.

    Students have no stored username field, so the portal login is derived from
    EmailAddress (e.g. 'jdoe@example.edu' -> 'jdoe').
    """
    if isinstance(email, str) and "@" in email:
        return email.split("@", 1)[0]
    return None


def roster_filter(section_id: int) -> str:
    """$filter for the StudentCourses collection: rows for one ClassSection."""
    return f"ClassSectionId eq {section_id}"


def roster_expand() -> str:
    return f"Student($select={ROSTER_STUDENT_SELECT})"


def flatten_roster_rows(
    student_courses: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten StudentCourse rows (with expanded Student) into roster dicts,
    sorted by student name. Student may be absent, so read it defensively.
    """
    flat: list[dict[str, Any]] = []
    for r in student_courses:
        stu = r.get("Student") or {}
        email = stu.get("EmailAddress")
        flat.append({
            "StudentCourseId": r.get("Id"),
            "StudentId": r.get("StudentId"),
            "StudentNumber": stu.get("StudentNumber"),
            "StudentName": stu.get("FullName"),
            # No stored username field on Student — derive it from the email.
            "StudentUsername": _email_localpart(email),
            "StudentEmail": email,
            "Status": r.get("Status"),
            "AddedOn": r.get("CreatedDateTime"),
            "LetterGrade": r.get("LetterGrade"),
            "NumericGrade": r.get("NumericGrade"),
        })
    flat.sort(key=lambda x: str(x.get("StudentName") or ""))
    return flat


def student_lookup_filter(
    *, student_id: int | None = None, email: str | None = None,
    username: str | None = None,
) -> str:
    """Build the $filter to find a student in the Students collection.

    - student_id -> "Id eq <n>" (the Student's own key)
    - email      -> case-insensitive exact match on EmailAddress
    - username   -> there is no username field; match the email local-part, i.e.
      EmailAddress beginning '<username>@' (case-insensitive). Mirrors how the roster
      derives StudentUsername from the email.
    """
    if student_id is not None:
        return f"Id eq {student_id}"
    if email:
        return f"tolower(EmailAddress) eq '{odata_quote(email.lower())}'"
    if username:
        return f"startswith(tolower(EmailAddress),'{odata_quote(username.lower())}@')"
    raise ValueError("Provide one of: student_id, email, or username.")


def by_student_filter(student_id: int, *, term_id: int | None = None) -> str:
    """$filter selecting rows for one student, by the StudentId foreign key.

    Used for both the course history (StudentCourses) and the ledger
    (StudentAccountTransactions) — note this is StudentId, not the Student's own
    Id key (the Students collection is filtered with 'Id eq <id>'). Both entities
    also carry a TermId, so an optional term_id narrows either to one term.
    """
    clause = f"StudentId eq {student_id}"
    if term_id is not None:
        clause += f" and TermId eq {term_id}"
    return clause


def flatten_student_courses(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten a student's StudentCourse rows (Course/Term expanded) into the
    course-history shape, sorted by term then course code."""
    flat: list[dict[str, Any]] = []
    for r in rows:
        course = r.get("Course") or {}
        term = r.get("Term") or {}
        flat.append({
            "StudentCourseId": r.get("Id"),
            "TermCode": term.get("Code"),
            "CourseCode": course.get("Code"),
            "CourseName": course.get("Name"),
            "Status": r.get("Status"),
            "LetterGrade": r.get("LetterGrade"),
            "NumericGrade": r.get("NumericGrade"),
            "AddedOn": r.get("CreatedDateTime"),
        })
    flat.sort(key=lambda x: (str(x.get("TermCode") or ""),
                             str(x.get("CourseCode") or "")))
    return flat


def flatten_ledger(
    rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    """Flatten StudentAccountTransaction rows into ledger lines (sorted by date)
    and return (lines, balance). Balance is the signed sum of TransactionAmount:
    charges are positive, credits/waivers negative, so the total is what's owed."""
    flat: list[dict[str, Any]] = []
    balance = 0.0
    for r in rows:
        amount = r.get("TransactionAmount") or 0
        balance += amount
        flat.append({
            "TransactionId": r.get("Id"),
            "TransactionDate": r.get("TransactionDate"),
            "PostDate": r.get("PostDate"),
            "Type": r.get("Type"),
            "Code": r.get("BillingTransactionCode"),
            "Description": r.get("Description"),
            "Amount": amount,
            "AmountPaid": r.get("AmountPaid"),
        })
    flat.sort(key=lambda x: str(x.get("TransactionDate") or ""))
    return flat, round(balance, 2)


def section_term_filter(
    *, code: str | None = None, code_prefix: str | None = None,
    term_id: int | None = None,
) -> str:
    """Build the $filter for ClassSectionTerms from one selector."""
    if term_id is not None:
        return f"TermId eq {term_id}"
    if code_prefix:
        return f"startswith(TermCode,'{odata_quote(code_prefix)}')"
    if code:
        return f"TermCode eq '{odata_quote(code)}'"
    raise ValueError("Provide one of: term_id, code_prefix, or code.")


def section_expand() -> str:
    """Expand the ClassSection plus its Instructor -> Staff -> Person chain.

    A 3-level nested $expand; the provider accepts it. Instructor/Staff/Person
    may each be absent (section with no instructor assigned), so flatten_section_rows
    reads every level defensively.
    """
    person = f"Person($select={INSTRUCTOR_PERSON_SELECT})"
    staff = f"Staff($select={INSTRUCTOR_STAFF_SELECT};$expand={person})"
    instructor = f"Instructor($select={INSTRUCTOR_SELECT};$expand={staff})"
    course = f"Course($select={COURSE_SELECT})"
    campus = f"Campus($select={CAMPUS_SELECT})"
    delivery = f"DeliveryMethod($select={DELIVERY_METHOD_SELECT})"
    nested = f"{instructor},{course},{campus},{delivery}"
    return f"ClassSection($select={SECTION_SELECT};$expand={nested})"


def _seats_open(cap: Any, registered: Any) -> int | None:
    """Seats remaining for a section, or None if either count is missing.

    The ClassSection entity has no stored "open" flag, so openness is derived:
    a positive value means the section can still take registrations (capacity
    minus currently registered students). Clamped at 0 for over-enrolled sections.
    """
    if isinstance(cap, int) and isinstance(registered, int):
        return max(cap - registered, 0)
    return None


def flatten_section_rows(
    join_rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Flatten ClassSectionTerms rows (with expanded ClassSection) into flat
    dicts, deduped on ClassSectionId. Returns (unique_rows, per_term_counts).

    A section can appear under multiple sub-terms, so we count every join row
    in per_term but keep each ClassSectionId once in the output.
    """
    seen: set = set()
    flat: list[dict[str, Any]] = []
    per_term: dict[str, int] = {}

    for r in join_rows:
        code = r.get("TermCode", "")
        per_term[code] = per_term.get(code, 0) + 1
        sid = r.get("ClassSectionId")
        if sid in seen:
            continue
        seen.add(sid)
        sec = r.get("ClassSection") or {}
        course = sec.get("Course") or {}
        campus = sec.get("Campus") or {}
        delivery = sec.get("DeliveryMethod") or {}
        inst = sec.get("Instructor") or {}
        staff = inst.get("Staff") or {}
        person = staff.get("Person") or {}
        flat.append({
            "ClassSectionId": sid,
            "TermId": r.get("TermId"),
            "TermCode": r.get("TermCode"),
            "TermName": r.get("TermName"),
            "CourseCode": sec.get("CourseCode"),
            "SectionCode": sec.get("SectionCode"),
            "SectionName": sec.get("SectionName"),
            "SectionStartDate": sec.get("StartDate"),
            "SectionEndDate": sec.get("EndDate"),
            # Course catalog detail: Name is the title, Note the description.
            "CourseName": course.get("Name"),
            "CourseCreditHours": course.get("CreditHours"),
            "CourseClockHours": course.get("ClockHours"),
            "CourseDescription": course.get("Note"),
            "IsActive": sec.get("IsActive"),
            "IsCancelled": sec.get("IsCancelled"),
            "MaximumStudents": sec.get("MaximumStudents"),
            "NumberRegisteredStudents": sec.get("NumberRegisteredStudents"),
            # Derived: ClassSection has no "open" flag — seats left = cap - registered.
            "SeatsOpen": _seats_open(sec.get("MaximumStudents"),
                                     sec.get("NumberRegisteredStudents")),
            "CampusId": sec.get("CampusId"),
            # Resolved location/modality (Campus + DeliveryMethod lookup entities).
            "CampusCode": campus.get("Code"),
            "CampusName": campus.get("Name"),
            "DeliveryMethodCode": delivery.get("Code"),
            "DeliveryMethod": delivery.get("Name"),
            "CourseId": sec.get("CourseId"),
            # Instructor detail (Instructor -> Staff -> Person). Falls back to the
            # section's own InstructorId FK when the Instructor wasn't expanded.
            "InstructorId": inst.get("InstructorId") or sec.get("InstructorId"),
            "InstructorStaffId": inst.get("StaffId"),
            "InstructorName": staff.get("FullName"),
            "InstructorEmail": staff.get("EmailAddress"),
            "InstructorPhone": staff.get("PhoneNumber"),
            "InstructorUsername": staff.get("Code"),
            "InstructorDob": person.get("DateOfBirth"),
        })

    flat.sort(key=lambda x: (str(x.get("CourseCode") or ""),
                             str(x.get("SectionCode") or "")))
    return flat, per_term
