import type { Metadata } from 'next';

import { LoginScreen } from '@/features/auth/login-screen';
import { INTERFACE_NAMES } from '@/lib/interface-names';

export const metadata: Metadata = {
  title: INTERFACE_NAMES.login,
};

export default function LoginPage() {
  return <LoginScreen />;
}
