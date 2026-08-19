/**
 * Approved bulk student import template and a demo file used by the prototype.
 *
 * BULK-01 limits the page to the approved CSV and XLSX templates. The column
 * headers below are the template. A CSV dropped on the page is parsed for real;
 * an XLSX file cannot be read in the browser prototype, so the demo rows here
 * are staged instead and the interface says so.
 */

export const IMPORT_TEMPLATE_COLUMNS = [
  'Student ID',
  'First Name',
  'Last Name',
  'College',
  'Campus',
  'Qualification',
  // Approved 13 August 2026. CT means Credit Transfer.
  //
  // It sits before Group because it decides whether Group, Intake and Course
  // Duration Option apply at all: for a CT student all three are Not Applicable.
  //
  // This is the one field added to an otherwise unchanged bulk contract. CT
  // status cannot be derived from anything else in the file, and defaulting
  // every row to No would fabricate business data.
  'CT Student',
  // Approved 11 August 2026: `Group 1`...`Group N` for the ten group-enabled
  // qualifications, `N/A` for every other one. Ignored when CT Student is Yes.
  'Group',
  'CoE / Non-CoE',
  'Proposed Start Date',
  'Proposed End Date',
  'Personal Email',
  'Primary Phone',
] as const;

/**
 * Demo rows. They deliberately contain one duplicate Student ID, one unmatched
 * college alias, one missing required value, one malformed date and four Group
 * problems, so that every SRS 7.3 status can be reviewed:
 *
 *  - ST20261115 SIT50422 with `Group 16`  -> above the approved maximum
 *  - ST20261116 SIT30821 with `N/A`       -> a group-enabled qualification needs a group
 *  - ST20261117 BSB50420 with `Group 3`   -> a non-group qualification must be N/A
 *  - ST20261118 RII50520 with `G2`        -> not the approved `Group n` form
 */
export const DEMO_IMPORT_CSV = [
  IMPORT_TEMPLATE_COLUMNS.join(','),
  'ST20261101,Hasan,Mahmud,AIBT Global,Melbourne,BSB50420,No,N/A,CoE,2026-09-07,2027-09-06,hasan.mahmud@example.com,0413 220 101',
  'ST20261102,Yuki,Tanaka,AIBT Global,Melbourne,BSB50420,No,N/A,CoE,2026-09-07,2027-09-06,yuki.tanaka@example.com,0413 220 102',
  'ST20261103,Nadia,Rahman,AIBT Global,Hobart,BSB60420,No,N/A,CoE,2026-09-07,2027-09-06,nadia.rahman@example.com,0413 220 103',
  'ST20261104,Peter,Novak,AIBT International,Sydney,BSB50820,No,N/A,CoE,2026-09-14,2027-03-15,peter.novak@example.com,0413 220 104',
  'ST20261105,Aisha,Bello,AIBT International,Sydney,CHC50125,No,N/A,CoE,2026-09-14,2028-03-13,aisha.bello@example.com,0413 220 105',
  'ST20261106,Ravi,Deshmukh,AIBT-I,Sydney,BSB50420,No,N/A,CoE,2026-09-14,2027-09-13,ravi.deshmukh@example.com,0413 220 106',
  'ST20261107,Elena,Petrova,AIBT Global,Brisbane,BSB50420,No,N/A,Non-CoE,2026-09-21,2027-03-22,elena.petrova@example.com,0413 220 107',
  'ST20261102,Yuki,Tanaka,AIBT Global,Melbourne,BSB50420,No,N/A,CoE,2026-09-07,2027-09-06,yuki.tanaka@example.com,0413 220 102',
  'ST20261109,Miguel,,AIBT Global,Melbourne,SIT30821,No,Group 2,CoE,2026-09-21,2027-09-20,miguel.torres@example.com,0413 220 109',
  ',Grace,Adeyemi,AIBT Global,Hobart,SIT30821,No,Group 3,CoE,2026-09-21,2027-09-20,grace.adeyemi@example.com,0413 220 110',
  'ST20261111,Chloe,Martin,AIBT Global,Hobart,BSB60420,No,N/A,CoE,21/09/2026,2027-09-20,chloe.martin@example.com,0413 220 111',
  'ST20261112,Omar,Haddad,Australian Vocational Institute,Perth,AUR30620,No,N/A,CoE,2026-09-28,2028-09-25,omar.haddad@example.com,0413 220 112',
  'ST20261113,Linh,Pham,Australian Vocational Institute,Perth,BSB50820,No,N/A,CoE,2026-09-28,2027-03-29,linh.pham@example.com,0413 220 113',
  'ST20261114,Daniel,Reyes,AIBT Global,Melbourne,BSB99999,No,N/A,CoE,2026-09-28,2027-09-27,daniel.reyes@example.com,0413 220 114',
  'ST20261115,Sara,Kovac,AIBT International,Adelaide,SIT50422,No,Group 16,CoE,2026-10-05,2028-04-02,sara.kovac@example.com,0413 220 115',
  'ST20261116,Tomas,Silva,AIBT Global,Melbourne,SIT30821,No,N/A,CoE,2026-10-05,2027-10-04,tomas.silva@example.com,0413 220 116',
  'ST20261117,Priya,Nair,AIBT Global,Melbourne,BSB50420,No,Group 3,CoE,2026-10-12,2027-10-11,priya.nair@example.com,0413 220 117',
  'ST20261118,Mateo,Rossi,AIBT International,Adelaide,SIT50422,No,G2,CoE,2026-10-12,2028-04-08,mateo.rossi@example.com,0413 220 118',
  'ST20261119,Sofia,Ricci,AIBT Global,Melbourne,BSB50420,Yes,,CoE,2026-10-05,2027-04-04,sofia.ricci@example.com,0413 220 119',
  'ST20261120,Arun,Pillai,AIBT Global,Hobart,SIT50422,Yes,Group 4,CoE,2026-10-05,2027-10-04,arun.pillai@example.com,0413 220 120',
].join('\n');

export const DEMO_IMPORT_FILE_NAME = 'bulk-student-import-demo.csv';
