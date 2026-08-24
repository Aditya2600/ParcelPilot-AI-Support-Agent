import { NextResponse } from "next/server";

// Frontend container liveness/readiness probe. Deliberately independent of the
// FastAPI backend -- that dependency is already surfaced in-app via apiHealthOk
// (see page.tsx), and a Docker healthcheck should reflect whether the Next
// server itself is serving requests, not whether an external service is up.
export function GET() {
  return NextResponse.json({ status: "ok" });
}
