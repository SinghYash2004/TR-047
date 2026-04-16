"use client";

import type { ReactNode } from "react";
import { type ChangeEvent, useMemo, useState } from "react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

type TimelineEvent = {
  time: string;
  title: string;
  detail: string;
  source: string;
};

type ReportState = {
  timeline: TimelineEvent[];
  incidentId?: string;
  rootCause: string;
  confidence: number;
  impact: {
    services: string[];
    downtime: string;
    severity: string;
  };
  postmortem: {
    summary: string;
    rca: string;
    actions: string[];
  };
};

type ApiReportResponse = {
  incident_id?: string;
  incident_window: {
    start: string;
    end: string;
  };
  timeline: TimelineEvent[];
  root_cause: string;
  confidence: number;
  impact: {
    affected_services: string[];
    estimated_downtime: string;
    severity: string;
  };
  postmortem: {
    summary: string;
    timeline_summary: string;
    rca: string;
    action_items: string[];
  };
  source_count: number;
};

const demoReport: ReportState = {
  timeline: [
    {
      time: "09:14:03",
      title: "Latency spike detected on API gateway",
      detail: "Application logs show rising request queue depth and 5xx responses from checkout.",
      source: "app.log"
    },
    {
      time: "09:16:18",
      title: "Database connection pool saturation",
      detail: "DB logs record repeated timeout errors after a burst of long-running inventory queries.",
      source: "db.log"
    },
    {
      time: "09:18:41",
      title: "Autoscaling lag increased error rate",
      detail: "Server metrics indicate CPU saturation and delayed pod scale-up during the incident window.",
      source: "server-metrics.log"
    },
    {
      time: "09:24:12",
      title: "Recovery initiated",
      detail: "Traffic normalized after query cancellation and manual pool reset on the database tier.",
      source: "ops-notes"
    }
  ],
  rootCause:
    "A slow inventory query cascade exhausted the database connection pool, which propagated upstream as gateway latency and checkout failures before autoscaling could absorb traffic.",
  confidence: 0.89,
  impact: {
    services: ["Checkout API", "Inventory Service", "Customer Dashboard"],
    downtime: "10 minutes full degradation, 18 minutes elevated latency",
    severity: "SEV-2"
  },
  postmortem: {
    summary:
      "The platform experienced a transactional slowdown caused by a query storm in the inventory database. Automated scaling reacted too slowly, amplifying customer-facing failures in checkout flows.",
    rca:
      "The most probable failure chain begins with unbounded inventory reads, continues into database pool exhaustion, and culminates in application timeouts across dependent services.",
    actions: [
      "Add circuit breaking and query timeout guards for inventory lookups.",
      "Pre-warm database connection pools during traffic surges.",
      "Create alerting on queue depth, timeout bursts, and scale-out lag correlation."
    ]
  }
};

function formatTimestamp(value: string) {
  if (!value) {
    return "Not selected";
  }

  return new Date(value).toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function toIsoTimestamp(value: string) {
  return new Date(value).toISOString();
}

function formatTimelineTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [startTime, setStartTime] = useState("2026-04-16T09:10");
  const [endTime, setEndTime] = useState("2026-04-16T09:30");
  const [architecture, setArchitecture] = useState(
    "Customer requests pass through an API gateway to Node.js services, PostgreSQL, Redis cache, and a Kubernetes-hosted worker tier."
  );
  const [isGenerating, setIsGenerating] = useState(false);
  const [report, setReport] = useState<ReportState | null>(demoReport);
  const [errorMessage, setErrorMessage] = useState("");

  const totalFilesSize = useMemo(
    () => files.reduce((sum, file) => sum + file.size, 0),
    [files]
  );

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files ?? []);
    setFiles((currentFiles) => {
      const nextFiles = [...currentFiles];

      for (const selectedFile of selectedFiles) {
        const alreadyAdded = nextFiles.some(
          (file) =>
            file.name === selectedFile.name &&
            file.size === selectedFile.size &&
            file.lastModified === selectedFile.lastModified
        );

        if (!alreadyAdded) {
          nextFiles.push(selectedFile);
        }
      }

      return nextFiles;
    });
    event.target.value = "";
  };

  const removeFile = (targetFile: File) => {
    setFiles((currentFiles) =>
      currentFiles.filter(
        (file) =>
          !(
            file.name === targetFile.name &&
            file.size === targetFile.size &&
            file.lastModified === targetFile.lastModified
          )
      )
    );
  };

  const generateReport = async () => {
    if (files.length === 0) {
      setErrorMessage("Attach one or more log files before generating a report.");
      return;
    }

    setErrorMessage("");
    setIsGenerating(true);

    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      formData.append("start_timestamp", toIsoTimestamp(startTime));
      formData.append("end_timestamp", toIsoTimestamp(endTime));
      formData.append("architecture_context", architecture);

      const response = await fetch(`${API_BASE_URL}/api/incidents/report`, {
        method: "POST",
        body: formData
      });

      const payload = (await response.json()) as ApiReportResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : "The backend could not generate the report."
        );
      }

      setReport(mapApiReportToUiReport(payload as ApiReportResponse));
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Unable to reach the backend. Make sure the API server is running."
      );
      setReport(demoReport);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <main className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-8 px-4 py-6 sm:px-6 lg:px-8">
      <section className="overflow-hidden rounded-[32px] border border-white/10 bg-white/5 shadow-panel backdrop-blur-xl">
        <div className="grid gap-8 px-6 py-8 lg:grid-cols-[1.15fr_0.85fr] lg:px-10 lg:py-10">
          <div className="space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-signal/30 bg-signal/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] text-signal">
              Autonomous Log-to-Incident Report Generator
            </div>
            <div className="space-y-4">
              <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-white sm:text-5xl">
                AI-powered incident reconstruction from scattered logs.
              </h1>
              <p className="max-w-2xl text-sm leading-7 text-slate-300 sm:text-base">
                Upload logs from multiple systems, define the incident window, and generate a
                structured postmortem with correlated timelines, root-cause analysis, impact, and
                follow-up actions.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard label="Supported inputs" value="App, DB, metrics" />
              <StatCard label="Outputs" value="Timeline + RCA" />
              <StatCard label="Engineer review" value="1-5 quality score" />
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-ink/70 p-5">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-300">Incident intake</p>
                <p className="text-xs text-slate-500">Configure the context for analysis</p>
              </div>
              <div className="rounded-full border border-amber-400/25 bg-amber-300/10 px-3 py-1 text-xs font-medium text-amber-200">
                AI correlation ready
              </div>
            </div>

            <div className="space-y-5">
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate-200">Upload log files</span>
                <div className="rounded-3xl border border-dashed border-slate-600 bg-slate-900/70 p-4 transition hover:border-signal/60 hover:bg-slate-900">
                  <input
                    multiple
                    accept=".log,.txt,text/plain"
                    type="file"
                    onChange={handleFiles}
                    className="block w-full cursor-pointer text-sm text-slate-300 file:mr-4 file:rounded-full file:border-0 file:bg-signal file:px-4 file:py-2 file:text-sm file:font-semibold file:text-slate-950 hover:file:bg-teal-300"
                  />
                  <p className="mt-3 text-xs text-slate-500">
                    Select multiple application logs, server metrics, DB traces, or plain text
                    incident exports. You can add more files in batches.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1">
                      {files.length} files selected
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1">
                      {(totalFilesSize / 1024).toFixed(1)} KB total
                    </span>
                  </div>
                </div>
              </label>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-200">Start timestamp</span>
                  <input
                    type="datetime-local"
                    value={startTime}
                    onChange={(event) => setStartTime(event.target.value)}
                    className="w-full rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none ring-0 transition focus:border-signal"
                  />
                </label>
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate-200">End timestamp</span>
                  <input
                    type="datetime-local"
                    value={endTime}
                    onChange={(event) => setEndTime(event.target.value)}
                    className="w-full rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none ring-0 transition focus:border-signal"
                  />
                </label>
              </div>

              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate-200">
                  System architecture context
                </span>
                <textarea
                  rows={5}
                  value={architecture}
                  onChange={(event) => setArchitecture(event.target.value)}
                  placeholder="Describe services, dependencies, and infrastructure topology."
                  className="w-full rounded-3xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm leading-6 text-slate-100 outline-none transition focus:border-signal"
                />
              </label>

              <button
                type="button"
                onClick={generateReport}
                className="flex w-full items-center justify-center rounded-2xl bg-gradient-to-r from-signal via-teal-300 to-cyan-300 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-70"
                disabled={isGenerating}
              >
                {isGenerating ? "Correlating events..." : "Generate Report"}
              </button>
              {errorMessage ? (
                <div className="rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                  {errorMessage}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="space-y-6">
          <Panel title="Incident Window" subtitle="Selected analysis scope">
            <div className="space-y-4">
              <InfoRow label="Start" value={formatTimestamp(startTime)} />
              <InfoRow label="End" value={formatTimestamp(endTime)} />
              <InfoRow label="Files attached" value={String(files.length)} />
              <InfoRow
                label="Payload size"
                value={`${(totalFilesSize / 1024).toFixed(1)} KB`}
              />
            </div>
          </Panel>

          <Panel title="Uploaded Sources" subtitle="Current log bundle">
            <div className="space-y-3">
              {files.length > 0 ? (
                files.map((file) => (
                  <div
                    key={`${file.name}-${file.lastModified}`}
                    className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-100">{file.name}</p>
                      <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-signal/10 px-3 py-1 text-xs text-signal">
                        queued
                      </span>
                      <button
                        type="button"
                        onClick={() => removeFile(file)}
                        className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300 transition hover:border-ember/40 hover:text-rose-200"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState
                  title="No files uploaded yet"
                  description="Attach one or more logs to populate the analysis pipeline."
                />
              )}
            </div>
          </Panel>

          <Panel title="Architecture Context" subtitle="System overview supplied to the model">
            <p className="text-sm leading-7 text-slate-300">{architecture || "No context added yet."}</p>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Correlated Timeline" subtitle="Events leading to the incident">
            <div className="space-y-5">
              {report?.timeline.map((event, index) => (
                <div key={`${event.time}-${index}`} className="flex gap-4">
                  <div className="flex flex-col items-center">
                    <div className="h-3 w-3 rounded-full bg-signal shadow-[0_0_0_6px_rgba(94,234,212,0.12)]" />
                    {index !== report.timeline.length - 1 ? (
                      <div className="mt-2 h-full w-px bg-gradient-to-b from-signal/50 to-transparent" />
                    ) : null}
                  </div>
                  <div className="flex-1 rounded-3xl border border-white/10 bg-white/[0.04] p-4">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-slate-100">{event.title}</h3>
                      <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
                        {formatTimelineTime(event.time)}
                      </span>
                    </div>
                    <p className="text-sm leading-6 text-slate-300">{event.detail}</p>
                    <p className="mt-3 text-xs text-signal">Source: {event.source}</p>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Root Cause Analysis" subtitle="Most likely failure chain">
              <div className="space-y-4">
                <p className="text-sm leading-7 text-slate-300">{report?.rootCause}</p>
                <div className="rounded-2xl border border-amber-300/20 bg-amber-300/10 p-4">
                  <p className="text-xs uppercase tracking-[0.24em] text-amber-200">Confidence</p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {Math.round((report?.confidence ?? 0) * 100)}%
                  </p>
                </div>
              </div>
            </Panel>

            <Panel title="Impact Assessment" subtitle="Affected scope and downtime">
              <div className="space-y-4">
                <InfoRow
                  label="Affected services"
                  value={report?.impact.services.join(", ") ?? "Not available"}
                />
                <InfoRow label="Estimated downtime" value={report?.impact.downtime ?? "Not available"} />
                <InfoRow label="Severity" value={report?.impact.severity ?? "Not available"} />
              </div>
            </Panel>
          </div>

          <Panel title="Auto-Generated Postmortem" subtitle="Structured report for IT operations">
            <div className="grid gap-4 lg:grid-cols-2">
              <PostmortemCard
                heading="Summary"
                content={report?.postmortem.summary ?? "No summary available yet."}
              />
              <PostmortemCard
                heading="RCA"
                content={report?.postmortem.rca ?? "No root cause narrative available yet."}
              />
              <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-5 lg:col-span-2">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Action items</p>
                <div className="mt-4 grid gap-3">
                  {report?.postmortem.actions.map((action) => (
                    <div
                      key={action}
                      className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3 text-sm text-slate-200"
                    >
                      {action}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Panel>
        </div>
      </section>
    </main>
  );
}

function Panel({
  title,
  subtitle,
  children
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[28px] border border-white/10 bg-slate-950/50 p-5 shadow-panel backdrop-blur-sm sm:p-6">
      <div className="mb-5">
        <p className="text-lg font-semibold text-white">{title}</p>
        <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.05] px-4 py-5">
      <p className="text-xs uppercase tracking-[0.22em] text-slate-500">{label}</p>
      <p className="mt-3 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="max-w-[65%] text-right text-sm font-medium text-slate-100">{value}</span>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-900/40 px-4 py-8 text-center">
      <p className="text-sm font-medium text-slate-200">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
    </div>
  );
}

function PostmortemCard({ heading, content }: { heading: string; content: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{heading}</p>
      <p className="mt-4 text-sm leading-7 text-slate-300">{content}</p>
    </div>
  );
}

function mapApiReportToUiReport(payload: ApiReportResponse): ReportState {
  return {
    incidentId: payload.incident_id,
    timeline: payload.timeline,
    rootCause: payload.root_cause,
    confidence: payload.confidence,
    impact: {
      services: payload.impact.affected_services,
      downtime: payload.impact.estimated_downtime,
      severity: payload.impact.severity
    },
    postmortem: {
      summary: payload.postmortem.summary,
      rca: payload.postmortem.rca,
      actions: payload.postmortem.action_items
    }
  };
}
