"""Qualification unit sets supplied directly by the project owner.

    python scripts/set_supplied_qualification_units.py            # dry run
    python scripts/set_supplied_qualification_units.py --apply    # write

Qualification Data is the usual source for which units belong to a
qualification. Where it is incomplete, the full set is recorded here instead of
being inferred - and it is recorded rather than pasted into the workbook so the
supplied list, its date and its author stay visible in the repository.

BSB50120 needed this. Qualification Data listed 10 of its 99 units, while its
rolling timetable taught 10 more that the file omitted, so the queue held ten
suggestions asking whether those units belong. They do, and so do 79 others.

Additive only. A unit already stored keeps its title, and a stored link absent
from a supplied list is left alone - withdrawing a unit is a different decision
with different consequences, and `prune_unsourced_unit_links.py` owns it.

`delivery_order` is never written here. Only an approved rolling timetable
supplies a position, through the reference import (OD-07).

Core and elective were supplied alongside each unit and are deliberately not
stored: `qualification_units` has no column for it, and the distinction does not
change what the qualification teaches. It belongs in the source workbook.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.qualification import Qualification, QualificationUnit, Unit  # noqa: E402

#: Qualification code -> the units it teaches, as (unit code, unit title).
#:
#: BSB50120 Diploma of Business, 99 units, supplied 8 September 2026.
SUPPLIED: dict[str, list[tuple[str, str]]] = {
    "BSB50120": [
        ('BSBAUD411', 'Participate in quality audits'),
        ('BSBAUD513', 'Report on quality audits'),
        ('BSBAUD514', 'Interpret compliance requirements'),
        ('BSBAUD515', 'Evaluate and review compliance'),
        ('BSBCRT412', 'Articulate, present and debate ideas'),
        ('BSBCRT511', 'Develop critical thinking in others'),
        ('BSBCRT512', 'Originate and develop concepts'),
        ('BSBCRT611', 'Apply critical thinking for complex problem solving'),
        ('BSBDAT501', 'Analyse data'),
        ('BSBFIN501', 'Manage budgets and financial plans'),
        ('BSBFIN502', 'Manage financial compliance'),
        ('BSBFIN601', 'Manage organisational finances'),
        ('BSBHRM412', 'Support employee and industrial relations'),
        ('BSBHRM521', 'Facilitate performance development processes'),
        ('BSBHRM525', 'Manage recruitment and onboarding'),
        ('BSBHRM526', 'Manage payroll'),
        ('BSBHRM529', 'Coordinate separation and termination processes'),
        ('BSBHRM531', 'Coordinate health and wellness programs'),
        ('BSBINS501', 'Implement information and knowledge management systems'),
        ('BSBINS502', 'Coordinate data management'),
        ('BSBINS504', 'Maintain digital repositories'),
        ('BSBINS512', 'Monitor business records systems'),
        ('BSBINS513', 'Contribute to records management framework'),
        ('BSBINS514', 'Contribute to records retention and disposal schedule'),
        ('BSBINS515', 'Participate in archiving activities'),
        ('BSBINS601', 'Manage knowledge and information'),
        ('BSBLDR521', 'Lead the development of diverse workforces'),
        ('BSBLDR522', 'Manage people performance'),
        ('BSBLDR523', 'Lead and manage effective workplace relationships'),
        ('BSBLDR601', 'Lead and manage organisational change'),
        ('BSBLEG522', 'Apply legal principles in contract law matters'),
        ('BSBMKG541', 'Identify and evaluate marketing opportunities'),
        ('BSBMKG546', 'Develop social media engagement plans'),
        ('BSBMKG548', 'Forecast international market and business needs'),
        ('BSBMKG549', 'Profile and analyse consumer behaviour for international markets'),
        ('BSBMKG550', 'Promote products and services to international markets'),
        ('BSBOPS404', 'Implement customer service strategies'),
        ('BSBOPS501', 'Manage business resources'),
        ('BSBOPS502', 'Manage business operational plans'),
        ('BSBOPS503', 'Develop administrative systems'),
        ('BSBOPS504', 'Manage business risk'),
        ('BSBOPS505', 'Manage organisational customer service'),
        ('BSBOPS601', 'Develop and implement business plans'),
        ('BSBOPS602', 'Monitor corporate governance activities'),
        ('BSBPEF401', 'Manage personal health and wellbeing'),
        ('BSBPEF501', 'Manage personal and professional development'),
        ('BSBPEF502', 'Develop and use emotional intelligence'),
        ('BSBPMG430', 'Undertake project work'),
        ('BSBPMG530', 'Manage project scope'),
        ('BSBPMG537', 'Manage project procurement'),
        ('BSBPRC501', 'Manage procurement strategies'),
        ('BSBPRC502', 'Manage supplier relationships'),
        ('BSBPRC503', 'Manage international procurement'),
        ('BSBPRC504', 'Manage a supply chain'),
        ('BSBPRC505', 'Manage ethical procurement strategy'),
        ('BSBSTR501', 'Establish innovative work environments'),
        ('BSBSTR502', 'Facilitate continuous improvement'),
        ('BSBSTR503', 'Develop organisational policy'),
        ('BSBSTR601', 'Manage innovation and continuous improvement'),
        ('BSBSTR603', 'Develop business continuity plans'),
        ('BSBSUS412', 'Develop and implement workplace sustainability plans'),
        ('BSBSUS413', 'Evaluate and report on workplace sustainability'),
        ('BSBSUS511', 'Develop workplace policies and procedures for sustainability'),
        ('BSBSUS601', 'Lead corporate social responsibility'),
        ('BSBTEC403', 'Apply digital solutions to work processes'),
        ('BSBTEC404', 'Use digital technologies to collaborate in a work environment'),
        ('BSBTEC501', 'Develop and implement an e-commerce strategy'),
        ('BSBTEC601', 'Review organisational digital strategy'),
        ('BSBTWK401', 'Build and maintain business relationships'),
        ('BSBTWK501', 'Lead diversity and inclusion'),
        ('BSBTWK502', 'Manage team effectiveness'),
        ('BSBTWK503', 'Manage meetings'),
        ('BSBTWK601', 'Develop and maintain strategic business networks'),
        ('BSBWHS521', 'Ensure a safe workplace for a work area'),
        ('BSBXBD501', 'Develop big data strategy'),
        ('BSBXCM501', 'Lead communication in the workplace'),
        ('BSBXCS402', 'Promote workplace cyber security awareness and best practices'),
        ('BSBXDB501', 'Support staff members with disability in the workplace'),
        ('BSBXDB502', 'Adapt organisations to enhance accessibility for people with disability'),
        ('CUAPRE401', 'Implement preventive conservation activities'),
        ('DEFEVL001', 'Develop an evaluation program'),
        ('DEFEVL002', 'Evaluate and report collected information'),
        ('DEFEVL003', 'Maintain and enhance professional practice'),
        ('DEFEVL004', 'Evaluate a training and assessment system'),
        ('DEFEVL005', 'Evaluate a community based program'),
        ('DEFEVL006', 'Evaluate business performance'),
        ('PSPPCM008', 'Manage contract performance'),
        ('PSPPCM009', 'Finalise contracts'),
        ('PSPPCM010', 'Manage procurement risk'),
        ('PSPPCM012', 'Plan for procurement outcomes'),
        ('PSPPCM013', 'Make procurement decisions'),
        ('PSPPCM015', 'Conduct and manage coordinated procurement'),
        ('PSPPCM016', 'Plan and implement strategic sourcing'),
        ('PSPPCM017', 'Plan and implement procurement category management'),
        ('PSPPCM018', 'Conduct demand and procurement spend analysis'),
        ('SIRXECM003', 'Design an ecommerce site'),
        ('SIRXMGT005', 'Lead the development of business opportunities'),
        ('SIRXMKT006', 'Develop a social media strategy'),
        ('SIRXSLS004', 'Drive sales results'),
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    print(f"Supplied qualification units - {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role : {settings.runtime_identity}\n")

    with Session(engine) as session:
        for code, units in SUPPLIED.items():
            qualification = session.execute(
                select(Qualification).where(Qualification.qualification_code == code)
            ).scalars().first()
            if qualification is None:
                print(f"  {code}: SKIPPED - not an approved qualification")
                continue

            stored = {
                u.unit_code.upper(): u
                for u in session.execute(select(Unit)).scalars()
            }
            linked = {
                r[0].upper()
                for r in session.execute(
                    select(Unit.unit_code)
                    .join(QualificationUnit, QualificationUnit.unit_id == Unit.id)
                    .where(QualificationUnit.qualification_id == qualification.id)
                )
            }

            created_units = linked_now = 0
            for unit_code, unit_title in units:
                key = unit_code.upper()
                unit = stored.get(key)
                if unit is None:
                    unit = Unit(unit_code=unit_code, unit_title=unit_title, is_active=True)
                    session.add(unit)
                    session.flush()
                    stored[key] = unit
                    created_units += 1
                if key not in linked:
                    session.add(
                        QualificationUnit(
                            qualification_id=qualification.id,
                            unit_id=unit.id,
                            delivery_order=None,
                        )
                    )
                    linked.add(key)
                    linked_now += 1

            print(
                f"  {code}: {len(units)} supplied - {created_units} unit(s) created, "
                f"{linked_now} link(s) added, {len(units) - linked_now} already linked"
            )

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back - nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
