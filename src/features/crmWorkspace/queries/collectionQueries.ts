import { useQuery } from '@tanstack/react-query';
import { fetchCollectionStatus } from '@/services/api/insideSales';
import type { CollectionSyncStatus, InsideSalesCollectionFamily } from '@/services/api/insideSales';

const STALE_TIME_MS = 30_000;

export const collectionQueryKeys = {
  status: (family: InsideSalesCollectionFamily) =>
    ['inside-sales', 'collection-status', family] as const,
};

export function useCollectionStatus(family: InsideSalesCollectionFamily) {
  return useQuery<CollectionSyncStatus>({
    queryKey: collectionQueryKeys.status(family),
    queryFn: () => fetchCollectionStatus(family),
    staleTime: STALE_TIME_MS,
  });
}
