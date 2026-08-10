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
  'CoE / Non-CoE',
  'Proposed Start Date',
  'Proposed End Date',
  'Personal Email',
  'Primary Phone',
] as const;

/**
 * Demo rows. They deliberately contain one duplicate Student ID, one unmatched
 * college alias, one missing required value and one malformed date so that
 * every SRS 7.3 status can be reviewed.
 */
export const DEMO_IMPORT_CSV = [
  IMPORT_TEMPLATE_COLUMNS.join(','),
  'ST20261101,Hasan,Mahmud,AIBT Global,Melbourne,BSB50420,CoE,2026-09-07,2027-09-06,hasan.mahmud@example.com,0413 220 101',
  'ST20261102,Yuki,Tanaka,AIBT Global,Melbourne,BSB50420,CoE,2026-09-07,2027-09-06,yuki.tanaka@example.com,0413 220 102',
  'ST20261103,Nadia,Rahman,AIBT Global,Hobart,BSB60420,CoE,2026-09-07,2027-09-06,nadia.rahman@example.com,0413 220 103',
  'ST20261104,Peter,Novak,AIBT International,Sydney,BSB50820,CoE,2026-09-14,2027-03-15,peter.novak@example.com,0413 220 104',
  'ST20261105,Aisha,Bello,AIBT International,Sydney,CHC50125,CoE,2026-09-14,2028-03-13,aisha.bello@example.com,0413 220 105',
  'ST20261106,Ravi,Deshmukh,AIBT-I,Sydney,BSB50420,CoE,2026-09-14,2027-09-13,ravi.deshmukh@example.com,0413 220 106',
  'ST20261107,Elena,Petrova,AIBT Global,Brisbane,BSB50420,Non-CoE,2026-09-21,2027-03-22,elena.petrova@example.com,0413 220 107',
  'ST20261102,Yuki,Tanaka,AIBT Global,Melbourne,BSB50420,CoE,2026-09-07,2027-09-06,yuki.tanaka@example.com,0413 220 102',
  'ST20261109,Miguel,,AIBT Global,Melbourne,SIT30821,CoE,2026-09-21,2027-09-20,miguel.torres@example.com,0413 220 109',
  ',Grace,Adeyemi,AIBT Global,Hobart,SIT30821,CoE,2026-09-21,2027-09-20,grace.adeyemi@example.com,0413 220 110',
  'ST20261111,Chloe,Martin,AIBT Global,Hobart,BSB60420,CoE,21/09/2026,2027-09-20,chloe.martin@example.com,0413 220 111',
  'ST20261112,Omar,Haddad,Australian Vocational Institute,Perth,AUR30620,CoE,2026-09-28,2028-09-25,omar.haddad@example.com,0413 220 112',
  'ST20261113,Linh,Pham,Australian Vocational Institute,Perth,BSB50820,CoE,2026-09-28,2027-03-29,linh.pham@example.com,0413 220 113',
  'ST20261114,Daniel,Reyes,AIBT Global,Melbourne,BSB99999,CoE,2026-09-28,2027-09-27,daniel.reyes@example.com,0413 220 114',
  'ST20261115,Sara,Kovac,AIBT International,Adelaide,SIT50422,CoE,2026-10-05,2028-04-02,sara.kovac@example.com,0413 220 115',
].join('\n');

export const DEMO_IMPORT_FILE_NAME = 'bulk-student-import-demo.csv';
