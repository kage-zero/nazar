/** Throwaway credentials for the per-run E2E database. Not a real secret. */
export const OPERATOR = {
  email: 'e2e-operator@example.org',
  password: `e2e-pass-${process.env.NAZAR_E2E_RUN ?? 'local'}`,
};

export const OPERATOR_STATE = 'playwright/.auth/operator.json';
