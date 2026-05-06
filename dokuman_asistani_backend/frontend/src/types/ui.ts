export type LoadableStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error';

export type LoadableState<T> = {
  status: LoadableStatus;
  data?: T;
  message?: string;
  updatedAt?: string;
};
