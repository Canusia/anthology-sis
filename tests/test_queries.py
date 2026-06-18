"""Tests for the pure query logic — no network."""

from anthology_sis import queries as q


class TestTermSearchFilter:
    def test_order_independent(self):
        # Names are year-first ('2026 Fall'); 'Fall 2026' must still match.
        f = q.term_search_filter("Fall 2026")
        assert f == "contains(Name,'Fall') and contains(Name,'2026')"

    def test_single_word(self):
        assert q.term_search_filter("Fall") == "contains(Name,'Fall')"

    def test_escapes_quotes(self):
        assert "''" in q.term_search_filter("O'Brien")


class TestSectionTermFilter:
    def test_by_id(self):
        assert q.section_term_filter(term_id=904) == "TermId eq 904"

    def test_by_code(self):
        assert q.section_term_filter(code="2025-FA-HS") == "TermCode eq '2025-FA-HS'"

    def test_by_prefix(self):
        assert q.section_term_filter(code_prefix="2025-FA") == \
            "startswith(TermCode,'2025-FA')"

    def test_requires_a_selector(self):
        import pytest
        with pytest.raises(ValueError):
            q.section_term_filter()


class TestCourseFilter:
    def test_by_id(self):
        assert q.course_filter(course_id=131) == "Id eq 131"

    def test_by_code(self):
        assert q.course_filter(code="ART155") == "Code eq 'ART155'"

    def test_by_title_is_lowered_and_anded(self):
        # contains() is case-sensitive here, so both sides are lowered via tolower().
        f = q.course_filter(title="Art History")
        assert f == ("contains(tolower(Name),'art') and "
                     "contains(tolower(Name),'history')")

    def test_title_escapes_quotes(self):
        assert "''" in q.course_filter(title="O'Brien")

    def test_blank_title_raises(self):
        import pytest
        with pytest.raises(ValueError):
            q.course_filter(title="   ")

    def test_requires_a_selector(self):
        import pytest
        with pytest.raises(ValueError):
            q.course_filter()


class TestRoster:
    def test_filter_by_section(self):
        assert q.roster_filter(856) == "ClassSectionId eq 856"

    def test_flatten_hoists_student_and_sorts_by_name(self):
        rows = [
            {"Id": 328859, "StudentId": 18500, "Status": "P",
             "CreatedDateTime": "2024-03-06T14:58:56-05:00",
             "LetterGrade": "A", "NumericGrade": None,
             "Student": {"FullName": "Roe, Sam", "StudentNumber": "0000002"}},
            {"Id": 318105, "StudentId": 11035, "Status": "D",
             "CreatedDateTime": "2024-03-06T14:58:56-05:00",
             "LetterGrade": None, "NumericGrade": None,
             "Student": {"FullName": "Doe, Jane", "StudentNumber": "0000001",
                         "EmailAddress": "doej@example.edu"}},
        ]
        flat = q.flatten_roster_rows(rows)
        assert [r["StudentName"] for r in flat] == ["Doe, Jane", "Roe, Sam"]
        first = flat[0]
        assert first["StudentId"] == 11035
        assert first["StudentNumber"] == "0000001"
        assert first["Status"] == "D"
        assert first["AddedOn"] == "2024-03-06T14:58:56-05:00"
        # Username is derived from the email local-part (no stored username field).
        assert first["StudentEmail"] == "doej@example.edu"
        assert first["StudentUsername"] == "doej"

    def test_flatten_handles_missing_student_expand(self):
        flat = q.flatten_roster_rows([{"Id": 1, "StudentId": 9, "Status": "P"}])
        assert flat[0]["StudentName"] is None
        assert flat[0]["StudentNumber"] is None
        assert flat[0]["StudentEmail"] is None
        assert flat[0]["StudentUsername"] is None


class TestStudentLookup:
    def test_lookup_by_id(self):
        assert q.student_lookup_filter(student_id=787) == "Id eq 787"

    def test_lookup_by_email_is_lowered(self):
        assert q.student_lookup_filter(email="Jdoe@Example.edu") == \
            "tolower(EmailAddress) eq 'jdoe@example.edu'"

    def test_lookup_by_username_matches_local_part(self):
        assert q.student_lookup_filter(username="Jdoe") == \
            "startswith(tolower(EmailAddress),'jdoe@')"

    def test_lookup_requires_a_selector(self):
        import pytest
        with pytest.raises(ValueError):
            q.student_lookup_filter()

    def test_by_student_filter(self):
        assert q.by_student_filter(787) == "StudentId eq 787"

    def test_by_student_filter_with_term(self):
        assert q.by_student_filter(787, term_id=905) == \
            "StudentId eq 787 and TermId eq 905"

    def test_flatten_student_courses_hoists_and_sorts(self):
        rows = [
            {"Id": 2, "Status": "P", "LetterGrade": "B", "CreatedDateTime": "2024-01-02",
             "Course": {"Code": "BIO101", "Name": "Biology"},
             "Term": {"Code": "2024-SP"}},
            {"Id": 1, "Status": "D", "LetterGrade": None, "CreatedDateTime": "2023-09-01",
             "Course": {"Code": "ACC155", "Name": "Accounting"},
             "Term": {"Code": "2023-FA"}},
        ]
        flat = q.flatten_student_courses(rows)
        # sorted by term then course code
        assert [(r["TermCode"], r["CourseCode"]) for r in flat] == \
            [("2023-FA", "ACC155"), ("2024-SP", "BIO101")]
        assert flat[0]["CourseName"] == "Accounting"
        assert flat[0]["AddedOn"] == "2023-09-01"

    def test_flatten_student_courses_missing_expand(self):
        flat = q.flatten_student_courses([{"Id": 5, "Status": "P"}])
        assert flat[0]["CourseCode"] is None
        assert flat[0]["TermCode"] is None

    def test_flatten_ledger_balance_is_signed_sum(self):
        rows = [
            {"Id": 1, "TransactionDate": "2023-09-27", "TransactionAmount": 840.0,
             "BillingTransactionCode": "TUIT", "Description": "Tuition"},
            {"Id": 2, "TransactionDate": "2023-09-27", "TransactionAmount": -210.0,
             "BillingTransactionCode": "TUITWAIV", "Description": "Tuition Waiver"},
        ]
        lines, balance = q.flatten_ledger(rows)
        assert balance == 630.0
        assert lines[0]["Code"] == "TUIT"
        assert lines[0]["Amount"] == 840.0

    def test_flatten_ledger_empty(self):
        lines, balance = q.flatten_ledger([])
        assert lines == []
        assert balance == 0.0


class TestFlattenSectionRows:
    def test_dedupes_on_class_section_id(self):
        # Same section under two sub-terms -> one unique row, counted twice.
        rows = [
            {"ClassSectionId": 111944, "TermId": 904, "TermCode": "2025-FA-HS",
             "TermName": "2025 Fall-High School",
             "ClassSection": {"CourseCode": "CPT150", "SectionCode": "WF"}},
            {"ClassSectionId": 111944, "TermId": 905, "TermCode": "2025-FA-HS-YR",
             "TermName": "2025 Fall-High School-Year",
             "ClassSection": {"CourseCode": "CPT150", "SectionCode": "WF"}},
        ]
        flat, per_term = q.flatten_section_rows(rows)
        assert len(flat) == 1
        assert per_term == {"2025-FA-HS": 1, "2025-FA-HS-YR": 1}

    def test_hoists_section_fields(self):
        rows = [{
            "ClassSectionId": 113884, "TermId": 330, "TermCode": "1971-FALL",
            "TermName": "1971 Fall",
            "ClassSection": {
                "CourseCode": "CPT150", "SectionName": "Microcomputer Concepts",
                "SectionCode": "WF", "MaximumStudents": 24,
                "NumberRegisteredStudents": 0, "InstructorId": 1731,
            },
        }]
        flat, _ = q.flatten_section_rows(rows)
        row = flat[0]
        assert row["CourseCode"] == "CPT150"
        assert row["SectionName"] == "Microcomputer Concepts"
        assert row["MaximumStudents"] == 24

    def test_sorted_by_course_then_section(self):
        rows = [
            {"ClassSectionId": 2, "TermCode": "T", "ClassSection":
                {"CourseCode": "BIO101", "SectionCode": "B"}},
            {"ClassSectionId": 1, "TermCode": "T", "ClassSection":
                {"CourseCode": "ACC105", "SectionCode": "A"}},
        ]
        flat, _ = q.flatten_section_rows(rows)
        assert [r["CourseCode"] for r in flat] == ["ACC105", "BIO101"]

    def test_handles_missing_expand(self):
        # If ClassSection wasn't expanded, fields are None, not a crash.
        rows = [{"ClassSectionId": 5, "TermCode": "T"}]
        flat, _ = q.flatten_section_rows(rows)
        assert flat[0]["CourseCode"] is None

    def test_hoists_instructor_chain(self):
        # Instructor -> Staff -> Person nested expand is flattened to columns.
        rows = [{
            "ClassSectionId": 111277, "TermId": 874, "TermCode": "2025-SP-HS",
            "ClassSection": {
                "CourseCode": "ART155", "InstructorId": 1951,
                "Instructor": {
                    "InstructorId": 1951, "StaffId": 1951,
                    "Staff": {
                        "Code": "smithp@example.edu",
                        "EmailAddress": "smithp@example.edu",
                        "FullName": "Smith, Pat",
                        "PhoneNumber": "555-0100",
                        "Person": {"DateOfBirth": "1980-05-01T00:00:00-04:00"},
                    },
                },
            },
        }]
        flat, _ = q.flatten_section_rows(rows)
        row = flat[0]
        assert row["InstructorName"] == "Smith, Pat"
        assert row["InstructorEmail"] == "smithp@example.edu"
        assert row["InstructorId"] == 1951
        assert row["InstructorStaffId"] == 1951
        assert row["InstructorPhone"] == "555-0100"
        assert row["InstructorUsername"] == "smithp@example.edu"
        assert row["InstructorDob"] == "1980-05-01T00:00:00-04:00"

    def test_hoists_section_dates_and_course(self):
        # Section run dates plus Course catalog detail (Name=title, Note=description).
        rows = [{
            "ClassSectionId": 111277, "TermCode": "2025-SP-HS",
            "ClassSection": {
                "CourseCode": "ART155",
                "StartDate": "2025-02-03T00:00:00-05:00",
                "EndDate": "2025-05-23T23:59:59-04:00",
                "Course": {
                    "Name": "Introduction To Art History",
                    "CreditHours": 3.0, "ClockHours": 0.0,
                    "Note": "Surveys the history and stylistic development...",
                },
            },
        }]
        flat, _ = q.flatten_section_rows(rows)
        row = flat[0]
        assert row["SectionStartDate"] == "2025-02-03T00:00:00-05:00"
        assert row["SectionEndDate"] == "2025-05-23T23:59:59-04:00"
        assert row["CourseName"] == "Introduction To Art History"
        assert row["CourseCreditHours"] == 3.0
        assert row["CourseClockHours"] == 0.0
        assert row["CourseDescription"].startswith("Surveys the history")

    def test_hoists_campus_and_delivery_method(self):
        rows = [{"ClassSectionId": 111277, "TermCode": "T", "ClassSection": {
            "CampusId": 5,
            "Campus": {"Id": 5, "Code": "MAIN", "Name": "Example CCC"},
            "DeliveryMethod": {"Id": 13, "Code": "HSC", "Name": "High School"},
        }}]
        flat, _ = q.flatten_section_rows(rows)
        row = flat[0]
        assert row["CampusCode"] == "MAIN"
        assert row["CampusName"] == "Example CCC"
        assert row["DeliveryMethodCode"] == "HSC"
        assert row["DeliveryMethod"] == "High School"

    def test_campus_and_delivery_absent_are_none(self):
        flat, _ = q.flatten_section_rows([{"ClassSectionId": 1, "TermCode": "T",
                                           "ClassSection": {}}])
        assert flat[0]["CampusName"] is None
        assert flat[0]["DeliveryMethod"] is None

    def test_seats_open_derived_from_counts(self):
        rows = [{"ClassSectionId": 1, "TermCode": "T", "ClassSection":
                 {"MaximumStudents": 24, "NumberRegisteredStudents": 20}}]
        flat, _ = q.flatten_section_rows(rows)
        assert flat[0]["SeatsOpen"] == 4

    def test_seats_open_clamps_and_handles_missing(self):
        rows = [
            {"ClassSectionId": 1, "TermCode": "T", "ClassSection":
                {"MaximumStudents": 10, "NumberRegisteredStudents": 12}},  # over-enrolled
            {"ClassSectionId": 2, "TermCode": "T", "ClassSection": {}},      # no counts
        ]
        flat, _ = q.flatten_section_rows(rows)
        by_id = {r["ClassSectionId"]: r for r in flat}
        assert by_id[1]["SeatsOpen"] == 0
        assert by_id[2]["SeatsOpen"] is None

    def test_instructor_id_falls_back_to_section_fk(self):
        # No nested Instructor expand: InstructorId still comes from the section,
        # and the Staff/Person-derived columns are None rather than a crash.
        rows = [{"ClassSectionId": 5, "TermCode": "T",
                 "ClassSection": {"InstructorId": 1731}}]
        flat, _ = q.flatten_section_rows(rows)
        assert flat[0]["InstructorId"] == 1731
        assert flat[0]["InstructorName"] is None
        assert flat[0]["InstructorDob"] is None
