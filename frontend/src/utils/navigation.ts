/**
 * Navigation Security and Internal Route Validation Utilities
 * Phase 2E.1: Robust Internal Route Fallback and Validation
 */

/**
 * Validates that a given destination URL is a safe, internal application route.
 * Rejects absolute external URLs, protocol-relative URLs, javascript URLs, data URLs,
 * and malicious encoded destinations.
 *
 * @param url The candidate destination string
 * @returns The sanitized internal route string, or null if invalid/malicious
 */
export function validateInternalReturnUrl(url: string | null | undefined): string | null {
  if (!url || typeof url !== "string") {
    return null;
  }

  const trimmed = url.trim();
  if (!trimmed) {
    return null;
  }

  // Reject dangerous schemes (javascript:, data:, vbscript:, file:, blob:)
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("javascript:") ||
    lower.startsWith("data:") ||
    lower.startsWith("vbscript:") ||
    lower.startsWith("file:") ||
    lower.startsWith("blob:") ||
    lower.startsWith("about:")
  ) {
    return null;
  }

  // Reject any string containing explicit protocol pattern (e.g., http://, https://, ftp://)
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(trimmed)) {
    return null;
  }

  // Reject protocol-relative URLs (//) and backslash variations (/\, \/, \\)
  if (
    trimmed.startsWith("//") ||
    trimmed.startsWith("/\\") ||
    trimmed.startsWith("\\\\") ||
    trimmed.startsWith("\\/")
  ) {
    return null;
  }

  // Reject encoded protocol-relative or backslash injection (%2f%2f, %5c)
  if (
    trimmed.includes("%2f%2f") ||
    trimmed.includes("%2F%2F") ||
    trimmed.includes("%5c") ||
    trimmed.includes("%5C") ||
    trimmed.includes("%252f") ||
    trimmed.includes("%252F")
  ) {
    return null;
  }

  // Must start with an internal route indicator: '/' or '?' or '#'
  if (!trimmed.startsWith("/") && !trimmed.startsWith("?") && !trimmed.startsWith("#")) {
    return null;
  }

  // Parse check with a fixed internal origin
  try {
    const dummyOrigin = "http://localhost";
    const parsed = new URL(trimmed, dummyOrigin);
    // Ensure origin was not spoofed
    if (parsed.origin !== dummyOrigin) {
      return null;
    }
  } catch {
    return null;
  }

  return trimmed;
}

export interface ComparisonNavigationState {
  jobId: string;
  jobTitle?: string;
  jobVersionId: string;
  revision: number;
  requirementsCount?: number;
  runId?: string;
  searchQuery?: string;
  resultsSearch?: string;
  page?: number;
  sortField?: "rank" | "score" | "name" | "evidence";
  sortDirection?: "asc" | "desc";
  selectedProfileIds?: string[];
  filterConfidence?: string;
}

/**
 * Validates that a candidate return URL is an approved internal processed-results route
 * and does not belong to a different job or match run.
 */
export function validateProcessedResultsReturnUrl(
  url: string | null | undefined,
  expectedJobId?: string,
  expectedRunId?: string
): string | null {
  const safeUrl = validateInternalReturnUrl(url);
  if (!safeUrl) {
    return null;
  }

  try {
    const dummyOrigin = "http://localhost";
    const parsed = new URL(safeUrl, dummyOrigin);

    // Extract query params
    const viewParam = parsed.searchParams.get("view");
    const jobIdParam = parsed.searchParams.get("jobId");
    const runIdParam = parsed.searchParams.get("runId");

    // Path check: must be root with query or approved job/match route
    const isApprovedRoute =
      parsed.pathname === "/" ||
      parsed.pathname.startsWith("/jobs") ||
      parsed.pathname.startsWith("/matches");

    if (!isApprovedRoute) {
      return null;
    }

    // If query specifies a view, it must be compare_candidates (the processed results view)
    if (viewParam && viewParam !== "compare_candidates") {
      return null;
    }

    // Verify job ID matches if specified in both
    if (expectedJobId && jobIdParam && jobIdParam !== expectedJobId) {
      return null;
    }

    // Verify run ID matches if specified in both
    if (expectedRunId && runIdParam && runIdParam !== expectedRunId) {
      return null;
    }

    return safeUrl;
  } catch {
    return null;
  }
}

