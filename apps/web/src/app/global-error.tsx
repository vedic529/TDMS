'use client';

import * as React from 'react';

/**
 * Last-resort boundary, for an error thrown by the root layout itself.
 *
 * It replaces the whole document, so it must render its own `<html>` and
 * `<body>` — the root layout is exactly what has failed. For the same reason it
 * uses inline styles and imports no component: anything it depended on might be
 * the thing that broke.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    console.error('TDMS fatal error:', error);
  }, [error]);

  return (
    <html lang="en-AU">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
          background: '#f8fafc',
          color: '#0f172a',
        }}
      >
        <main style={{ maxWidth: '28rem', padding: '2rem', textAlign: 'center' }}>
          <p style={{ fontSize: '0.75rem', letterSpacing: '0.08em', color: '#64748b' }}>TDMS</p>
          <h1 style={{ marginTop: '0.75rem', fontSize: '1.125rem', fontWeight: 600 }}>
            TDMS could not start
          </h1>
          <p style={{ marginTop: '0.75rem', fontSize: '0.85rem', lineHeight: 1.6, color: '#475569' }}>
            The application failed to load. Your data has not been changed. Reload the page, and if
            the problem continues contact the TDMS administrator with the reference below.
          </p>
          {error.digest && (
            <p
              style={{
                marginTop: '0.75rem',
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                fontSize: '0.75rem',
                color: '#64748b',
              }}
            >
              Reference: {error.digest}
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: '1.5rem',
              padding: '0.5rem 1rem',
              borderRadius: '0.5rem',
              border: '1px solid #cbd5e1',
              background: '#0f172a',
              color: '#f8fafc',
              fontSize: '0.85rem',
              cursor: 'pointer',
            }}
          >
            Reload TDMS
          </button>
        </main>
      </body>
    </html>
  );
}
