import type { CourseRecord, QualificationUnitSequence } from '@/types/reference';

/** Form value shapes shared by the reference screens and the real API adapter. */
export type CourseInput = Omit<CourseRecord, 'id' | 'isDeleted' | 'deletion'>;

export type QualificationUnitInput = Omit<
  QualificationUnitSequence,
  'id' | 'isDeleted' | 'deletion' | 'deliveryOrder' | 'recordId' | 'collegeId' | 'campusId'
>;
