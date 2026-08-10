import { env } from '@/lib/env';
import { ApiTdmsClient } from './api-tdms-client';
import { MockTdmsClient } from './mock-tdms-client';
import type { TdmsClient } from './tdms-client';

/**
 * Chooses the data service for the current environment.
 *
 *   NEXT_PUBLIC_TDMS_DATA_MODE=mock -> MockTdmsClient (prototype dataset)
 *   NEXT_PUBLIC_TDMS_DATA_MODE=api  -> ApiTdmsClient  (FastAPI service)
 *
 * A single instance is reused so the prototype dataset stays consistent across
 * pages during one browser session.
 */
let client: TdmsClient | null = null;

export function getTdmsClient(): TdmsClient {
  if (!client) {
    client = env.dataMode === 'api' ? new ApiTdmsClient(env.apiUrl) : new MockTdmsClient();
  }
  return client;
}

/** Used by the development tools after resetting demo data. */
export function resetTdmsClient(): void {
  client = null;
}

export type { TdmsClient, ActionContext, ReasonedRequest } from './tdms-client';
export type { ReferenceDataBundle, TdmsDataset } from './dataset';
