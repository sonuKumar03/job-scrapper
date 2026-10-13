import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "./api";

export function useRuns(page = 1, poll = true) {
  return useQuery({
    queryKey: ["runs", page],
    queryFn: ({ signal }) => fetchApi(`runs?page=${page}&page_size=25`, { signal }),
    refetchInterval: poll ? 5000 : false,
  });
}

export function useActiveRuns() {
  return useQuery({
    queryKey: ['runs', 'active'],
    queryFn: ({ signal }) => fetchApi('runs/active', { signal }),
    refetchInterval: 2000,
  });
}
