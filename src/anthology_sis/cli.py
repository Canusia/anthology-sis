"""Command-line interface for the Anthology SIS client.

    anthology-sis terms --search "fall 2026"
    anthology-sis sections --term-code 2025-FA-HS
    anthology-sis sections --term-prefix 2025-FA --out fall25.csv
    anthology-sis section --id 113884
"""

from __future__ import annotations

import argparse
import csv
import sys
import textwrap

from .client import ODataClient
from .config import Config, load_config
from . import queries as q


def _client(config: Config) -> ODataClient:
    return ODataClient(config)


def cmd_terms(config: Config, args: argparse.Namespace) -> int:
    client = _client(config)
    filter_ = args.filter or (q.term_search_filter(args.search) if args.search else None)
    rows = list(client.iter_collection(
        config.terms_path,
        select="Id,Code,Name,StartDate,EndDate,IsActive",
        filter_=filter_,
        orderby="StartDate desc",
        top=args.top,
    ))
    print(f"Retrieved {len(rows)} term(s).\n")
    for t in rows:
        print(f"  {str(t.get('Code') or t.get('Id')):<15} "
              f"{str(t.get('Name') or ''):<25} {t.get('StartDate', '')}")
    return 0


def cmd_sections(config: Config, args: argparse.Namespace) -> int:
    client = _client(config)
    filter_ = q.section_term_filter(
        code=args.term_code, code_prefix=args.term_prefix, term_id=args.term_id,
    )
    join_rows = client.iter_collection(
        config.sections_path,
        select="ClassSectionId,TermId,TermCode,TermName",
        filter_=filter_,
        expand=q.section_expand(),
        top=args.top,
    )
    flat, per_term = q.flatten_section_rows(join_rows)

    if flat:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=q.SECTION_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(flat)

    total = sum(per_term.values())
    print(f"Unique sections: {len(flat)}  (from {total} term-section rows)")
    if len(per_term) > 1:
        print("Per sub-term:")
        for code, n in sorted(per_term.items()):
            print(f"  {code:<18} {n}")
    if flat:
        print(f"\nWrote CSV -> {args.out}")
    return 0


def cmd_section(config: Config, args: argparse.Namespace) -> int:
    client = _client(config)
    section = client.get_entity(
        "ds/odata/ClassSections", args.id, expand=args.expand or None
    )
    # Also resolve the term via the join entity.
    terms = list(client.iter_collection(
        config.sections_path,
        select="TermId,TermCode,TermName",
        filter_=f"ClassSectionId eq {args.id}",
    ))
    print(f"Section {args.id}: {section.get('CourseCode')} "
          f"{section.get('SectionCode')} — {section.get('SectionName')}")
    print(f"  Active={section.get('IsActive')} "
          f"Cancelled={section.get('IsCancelled')} "
          f"Cap={section.get('MaximumStudents')} "
          f"Registered={section.get('NumberRegisteredStudents')}")
    if terms:
        for t in terms:
            print(f"  Term: {t.get('TermCode')} ({t.get('TermId')}) — {t.get('TermName')}")
    else:
        print("  Term: (no ClassSectionTerm row found)")
    return 0


def cmd_course(config: Config, args: argparse.Namespace) -> int:
    client = _client(config)
    filter_ = q.course_filter(
        course_id=args.id, code=args.code, title=args.title,
    )
    courses = list(client.iter_collection(
        "ds/odata/Courses",
        select=q.COURSE_DETAIL_SELECT,
        filter_=filter_,
        orderby="Code",
        top=args.top,
    ))
    if not courses:
        print("No matching course.")
        return 0
    print(f"Retrieved {len(courses)} course(s).\n")
    for c in courses:
        units = "clock" if (c.get("UnitType") or "").upper() == "C" else "credit"
        hours = c.get("ClockHours") if units == "clock" else c.get("CreditHours")
        print(f"  [{c.get('Id')}] {c.get('Code')} — {c.get('Name')}")
        print(f"      {hours} {units} hours   Active={c.get('IsActive')}   "
              f"CatalogCode={c.get('CatalogCode')}")
        note = (c.get("Note") or "").strip()
        if note:
            print("      " + textwrap.fill(note, width=92,
                                           subsequent_indent="      "))
        print()
    return 0


def cmd_roster(config: Config, args: argparse.Namespace) -> int:
    client = _client(config)
    rows = client.iter_collection(
        "ds/odata/StudentCourses",
        select=q.ROSTER_SELECT,
        filter_=q.roster_filter(args.section_id),
        expand=q.roster_expand(),
        top=args.top,
    )
    flat = q.flatten_roster_rows(rows)
    if not flat:
        print(f"No students registered in section {args.section_id}.")
        return 0

    print(f"Section {args.section_id}: {len(flat)} student(s)\n")
    print(f"  {'StudentNo':<10} {'Name':<26} {'Username':<14} {'Email':<30} "
          f"{'Status':<7} {'Grade':<6} Added")
    for r in flat:
        print(f"  {str(r['StudentNumber'] or ''):<10} {str(r['StudentName'] or ''):<26} "
              f"{str(r['StudentUsername'] or ''):<14} {str(r['StudentEmail'] or ''):<30} "
              f"{str(r['Status'] or ''):<7} {str(r['LetterGrade'] or ''):<6} "
              f"{str(r['AddedOn'] or '')[:10]}")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=q.ROSTER_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(flat)
        print(f"\nWrote CSV -> {args.out}")
    return 0


def cmd_student(config: Config, args: argparse.Namespace) -> int:
    client = _client(config)

    # Resolve the student by id, email, or username (username = email local-part).
    students = list(client.iter_collection(
        "ds/odata/Students", select=q.STUDENT_SELECT,
        filter_=q.student_lookup_filter(
            student_id=args.id, email=args.email, username=args.username),
        orderby="Id",
    ))
    if not students:
        print("No student matching that id/email/username.")
        return 0
    if len(students) > 1:
        print(f"{len(students)} students match — narrow with --id:")
        for m in students:
            print(f"  [{m.get('Id')}] {m.get('FullName')}  ({m.get('EmailAddress')})")
        return 0
    s = students[0]
    student_id = s["Id"]
    print(f"Student {student_id}: {s.get('FullName')}  "
          f"(#{s.get('StudentNumber')})  {s.get('EmailAddress')}")

    # Optional term scope: resolve --term-code to a TermId (applied to both sections).
    term_id = None
    if args.term_code:
        terms = list(client.iter_collection(
            config.terms_path, select="Id,Code",
            filter_=f"Code eq '{q.odata_quote(args.term_code)}'",
        ))
        if not terms:
            print(f"No term with code {args.term_code!r}.")
            return 0
        term_id = terms[0]["Id"]
        print(f"Scoped to term {args.term_code} (TermId {term_id}).")

    # Course history.
    courses = q.flatten_student_courses(client.iter_collection(
        "ds/odata/StudentCourses", select=q.STUDENT_COURSE_SELECT,
        filter_=q.by_student_filter(student_id, term_id=term_id),
        expand=q.STUDENT_COURSE_EXPAND,
    ))
    print(f"\nClasses taken: {len(courses)}")
    if courses:
        print(f"  {'Term':<14} {'Course':<10} {'Title':<34} {'Status':<7} "
              f"{'Grade':<6} Added")
        for r in courses:
            print(f"  {str(r['TermCode'] or ''):<14} {str(r['CourseCode'] or ''):<10} "
                  f"{str(r['CourseName'] or '')[:34]:<34} {str(r['Status'] or ''):<7} "
                  f"{str(r['LetterGrade'] or ''):<6} {str(r['AddedOn'] or '')[:10]}")

    # Financial ledger.
    ledger, balance = q.flatten_ledger(client.iter_collection(
        "ds/odata/StudentAccountTransactions", select=q.LEDGER_SELECT,
        filter_=q.by_student_filter(student_id, term_id=term_id),
    ))
    print(f"\nLedger: {len(ledger)} transaction(s)")
    if ledger:
        print(f"  {'Date':<12} {'Code':<10} {'Description':<32} {'Amount':>12}")
        for r in ledger:
            print(f"  {str(r['TransactionDate'] or '')[:10]:<12} "
                  f"{str(r['Code'] or ''):<10} {str(r['Description'] or '')[:32]:<32} "
                  f"{r['Amount']:>12.2f}")
        print(f"  {'':<10} {'':<10} {'Balance':>32} {balance:>12.2f}")

    if args.out_prefix:
        _write_csv(f"{args.out_prefix}-courses.csv", q.STUDENT_COURSE_CSV_FIELDS, courses)
        _write_csv(f"{args.out_prefix}-ledger.csv", q.LEDGER_CSV_FIELDS, ledger)
        print(f"\nWrote {args.out_prefix}-courses.csv and {args.out_prefix}-ledger.csv")
    return 0


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anthology-sis",
                                     description="Anthology Student Query API client.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_terms = sub.add_parser("terms", help="Query the Terms collection.")
    p_terms.add_argument("--search")
    p_terms.add_argument("--filter")
    p_terms.add_argument("--top", type=int)
    p_terms.set_defaults(func=cmd_terms)

    p_sec = sub.add_parser("sections", help="Query sections for a term.")
    g = p_sec.add_mutually_exclusive_group(required=True)
    g.add_argument("--term-code")
    g.add_argument("--term-prefix")
    g.add_argument("--term-id", type=int)
    p_sec.add_argument("--top", type=int)
    p_sec.add_argument("--out", default="sections.csv")
    p_sec.set_defaults(func=cmd_sections)

    p_one = sub.add_parser("section", help="Fetch one section by Id.")
    p_one.add_argument("--id", type=int, required=True)
    p_one.add_argument("--expand", help="e.g. Course,Campus,Instructor,Terms")
    p_one.set_defaults(func=cmd_section)

    p_course = sub.add_parser("course", help="Query a course by id, code, or title.")
    gc = p_course.add_mutually_exclusive_group(required=True)
    gc.add_argument("--id", type=int)
    gc.add_argument("--code", help="exact course code, e.g. ART155")
    gc.add_argument("--title", help="order-independent, case-insensitive name search")
    p_course.add_argument("--top", type=int)
    p_course.set_defaults(func=cmd_course)

    p_roster = sub.add_parser("roster", help="List students registered in a section.")
    p_roster.add_argument("--section-id", type=int, required=True,
                          help="ClassSection Id (e.g. from the sections command)")
    p_roster.add_argument("--top", type=int)
    p_roster.add_argument("--out", help="optional CSV path")
    p_roster.set_defaults(func=cmd_roster)

    p_student = sub.add_parser(
        "student", help="Look up a student (by id/email/username): history + ledger.")
    gs = p_student.add_mutually_exclusive_group(required=True)
    gs.add_argument("--id", type=int, help="Student Id")
    gs.add_argument("--email", help="exact email (case-insensitive)")
    gs.add_argument("--username", help="email local-part, e.g. jdoe")
    p_student.add_argument("--term-code",
                           help="scope history AND ledger to one term, e.g. 2023-FA-HS-YR")
    p_student.add_argument("--out-prefix",
                           help="write <prefix>-courses.csv and <prefix>-ledger.csv")
    p_student.set_defaults(func=cmd_student)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()
    try:
        return args.func(config, args)
    except (PermissionError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
