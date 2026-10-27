'use client';
import { useEffect, useState } from 'react';
import { api, warehouseRequestHeaders } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import { hasMenuPermission } from '@/hooks/useMenuPermission';

type Registry = Parameters<typeof hasMenuPermission>[2];

// Page status only: the existing permission function and backend remain the authority.
export function useSupplierAccess() {
  const { user, loading: authLoading } = useAuth();
  const scope = JSON.stringify([warehouseRequestHeaders(), user?.id, user?.role, user?.extra_permissions]);
  const needsRegistry = !!user && ['supervisor', 'staff', 'super_admin'].includes(user.role);
  const [snapshot, setSnapshot] = useState<{ scope: string; permissions: Registry } | null>(null);
  const [failure, setFailure] = useState<{ scope: string; message: string } | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setSnapshot(null); setFailure(null);
    if (needsRegistry) api.get<Registry>('/users/permissions').then(permissions => {
      if (!Array.isArray(permissions)) throw Error('权限清单格式异常');
      if (active) setSnapshot({ scope, permissions });
    }).catch((error: Error) => { if (active) setFailure({ scope, message: error.message || '权限清单读取失败' }); });
    return () => { active = false; };
  }, [scope, needsRegistry, revision]);
  const error = failure?.scope === scope ? failure.message : '';
  const loading = authLoading || (needsRegistry && snapshot?.scope !== scope && !error);
  return {
    scope, loading, error,
    can: (key: string) => !loading && !error && hasMenuPermission(user, key, snapshot?.scope === scope ? snapshot.permissions : []),
    retry: () => setRevision(value => value + 1),
  };
}
