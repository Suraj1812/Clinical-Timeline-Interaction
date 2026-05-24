import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bell,
  Check,
  Clock3,
  Pill,
  Trash2,
  Send,
  Stethoscope,
  Thermometer,
  X
} from "lucide-react";

import { api } from "./api";
import type { Actor, InstructionType, Task, TimelineEvent, TimelineState } from "./types";

const emptyState: TimelineState = { tasks: [], events: [] };

function formatTime(iso: string) {
  const date = new Date(iso);
  const now = new Date();

  const isToday = date.toDateString() === now.toDateString();

  const yesterday = new Date();
  yesterday.setDate(now.getDate() - 1);

  const isYesterday =
    date.toDateString() === yesterday.toDateString();

  const sameWeek =
    now.getTime() - date.getTime() < 7 * 24 * 60 * 60 * 1000;

  const time = new Intl.DateTimeFormat([], {
    hour: "numeric",
    minute: "2-digit",
    hour12: true
  }).format(date);

  if (isToday) {
    return `Today • ${time}`;
  }

  if (isYesterday) {
    return `Yesterday • ${time}`;
  }

  if (sameWeek) {
    return `${date.toLocaleDateString([], {
      weekday: "long"
    })} • ${time}`;
  }

  return `${date.toLocaleDateString([], {
    day: "numeric",
    month: "short"
  })} • ${time}`;
}

function eventIcon(event: TimelineEvent) {
  if (event.actor === "doctor") return <Stethoscope size={18} />;
  if (event.type === "temperature_recorded") return <Thermometer size={18} />;
  if (event.type === "alert_triggered") return <Bell size={18} />;
  if (event.type === "task_not_taken") return <X size={18} />;
  if (event.type === "task_completed") return <Check size={18} />;
  return <Activity size={18} />;
}

function actorLabel(actor: Actor) {
  if (actor === "doctor") return "Doctor";
  if (actor === "patient") return "Patient";
  return "System";
}

export default function App() {
  const [state, setState] = useState<TimelineState>(emptyState);
  const [temperature, setTemperature] = useState(102);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState("");

  const activeTask = useMemo(() => {
    return [...state.tasks].reverse().find((task) => task.status === "pending");
  }, [state.tasks]);

  const latestAlert = useMemo(() => {
    return [...state.events]
      .reverse()
      .find((event) => event.type === "alert_triggered");
  }, [state.events]);
  const eventCount = `${state.events.length} ${state.events.length === 1 ? "event" : "events"
    }`;

  async function runAction(label: string, action: () => Promise<TimelineState>) {
    setBusyAction(label);
    setError("");
    try {
      setState(await action());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong");
    } finally {
      setBusyAction(null);
    }
  }

  useEffect(() => {
    runAction("load", () => api<TimelineState>("/api/state"));
  }, []);

  const createTask = (type: InstructionType) => {
    runAction(`create-${type}`, () =>
      api<TimelineState>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ type })
      })
    );
  };

  const respondMedication = (outcome: "taken" | "not_taken") => {
    if (!activeTask) return;
    runAction(`medication-${outcome}`, () =>
      api<TimelineState>("/api/medication-response", {
        method: "POST",
        body: JSON.stringify({ task_id: activeTask.id, outcome })
      })
    );
  };

  const recordTemperature = () => {
    if (!activeTask) return;
    runAction("temperature", () =>
      api<TimelineState>("/api/temperature-response", {
        method: "POST",
        body: JSON.stringify({ task_id: activeTask.id, value: temperature })
      })
    );
  };

  const resetDemo = () => {
    runAction("reset", () =>
      api<TimelineState>("/api/reset", {
        method: "POST"
      })
    );
  };

  return (
    <main className="app-shell">
      <section className="top-band" aria-labelledby="app-title">
        <div className="case-title">
          <div>
            <p className="eyebrow">Svastra+ v0.9</p>
            <h1 id="app-title">Clinical Timeline</h1>
          </div>
        </div>
        <div className="status-line" aria-live="polite">
          <span>{eventCount}</span>
          <span className={latestAlert ? "status-alert" : ""}>
            {latestAlert ? "Alert active" : "No Alert"}
          </span>
          <button
            className="icon-button"
            type="button"
            onClick={resetDemo}
            disabled={busyAction === "reset"}
            aria-label="Reset timeline"
            title="Reset timeline"
            style={{
              color: "red",
              border: "1px solid red",
              borderWidth: "0.5px"
            }}
          >
            <Trash2 size={18} />
          </button>
        </div>
      </section>

      {error ? (
        <p className="error-message" role="alert">
          {error}
        </p>
      ) : null}

      <section className="workspace" aria-label="Clinical workflow">
        <aside className="action-rail">
          <DoctorActions
            busyAction={busyAction}
            hasActiveTask={Boolean(activeTask)}
            onCreate={createTask}
          />
          <PatientActions
            activeTask={activeTask}
            busyAction={busyAction}
            temperature={temperature}
            setTemperature={setTemperature}
            onMedication={respondMedication}
            onTemperature={recordTemperature}
          />
        </aside>
        <Timeline events={state.events} />
      </section>
    </main>
  );
}

function BrandLogo() {
  return (
    <svg
      className="brand-logo"
      viewBox="0 0 640 220"
      role="img"
      aria-labelledby="brand-logo-title"
    >
      <title id="brand-logo-title">BC2RI</title>
      <rect width="640" height="220" fill="#ffffff" />
      <g fill="#07167f">
        <text x="15" y="171" fontFamily="Georgia, 'Times New Roman', serif" fontSize="26">
          -∞
        </text>
        <text x="97" y="43" fontFamily="Georgia, 'Times New Roman', serif" fontSize="26">
          +∞
        </text>
        <text
          x="37"
          y="166"
          fontFamily="Georgia, 'Times New Roman', serif"
          fontSize="178"
          fontStyle="italic"
        >
          ∫
        </text>
        <text x="150" y="143" fontFamily="Georgia, 'Times New Roman', serif" fontSize="88">
          βC2Rí
        </text>
      </g>
    </svg>
  );
}

function DoctorActions({
  busyAction,
  hasActiveTask,
  onCreate
}: {
  busyAction: string | null;
  hasActiveTask: boolean;
  onCreate: (type: InstructionType) => void;
}) {
  const disabled = (busyAction !== null && busyAction !== "load") || hasActiveTask;

  return (
    <section className="panel" aria-labelledby="doctor-actions">
      <div className="panel-heading">
        <Stethoscope size={18} />
        <h2 id="doctor-actions">Doctor action</h2>
      </div>
      <div className="preset-grid">
        <button
          className="preset-button"
          type="button"
          onClick={() => onCreate("medication")}
          disabled={disabled}
        >
          <Pill size={20} />
          <span>Tab. Dolo 650</span>
          <small>1 tablet TDPC</small>
        </button>
        <button
          className="preset-button temp"
          type="button"
          onClick={() => onCreate("temperature")}
          disabled={disabled}
        >
          <Thermometer size={20} />
          <span>Record Temperature</span>
          <small>°F reading</small>
        </button>
      </div>
    </section>
  );
}

function PatientActions({
  activeTask,
  busyAction,
  temperature,
  setTemperature,
  onMedication,
  onTemperature
}: {
  activeTask?: Task;
  busyAction: string | null;
  temperature: number;
  setTemperature: (value: number) => void;
  onMedication: (outcome: "taken" | "not_taken") => void;
  onTemperature: () => void;
}) {
  return (
    <section className="panel patient-panel" aria-labelledby="patient-actions">
      <div className="panel-heading">
        <Activity size={18} />
        <h2 id="patient-actions">Patient response</h2>
      </div>

      {!activeTask ? (
        <div className="quiet-state">
          <Clock3 size={22} />
          <span>No pending task</span>
        </div>
      ) : activeTask.type === "medication" ? (
        <div className="response-stack">
          <p className="active-instruction">{activeTask.instruction}</p>
          <div className="choice-row">
            <button
              className="response-button positive"
              type="button"
              onClick={() => onMedication("taken")}
              disabled={busyAction !== null}
            >
              <Check size={20} />
              Taken
            </button>
            <button
              className="response-button danger"
              type="button"
              onClick={() => onMedication("not_taken")}
              disabled={busyAction !== null}
            >
              <X size={20} />
              Not taken
            </button>
          </div>
        </div>
      ) : (
        <div className="response-stack">
          <p className="active-instruction">{activeTask.instruction}</p>
          <div className="temperature-dial" aria-label="Temperature value">
            <strong>{temperature.toFixed(1)}°F</strong>
            <input
              type="range"
              min="96"
              max="104"
              step="0.1"
              value={temperature}
              aria-label="Temperature in Fahrenheit"
              aria-valuetext={`${temperature.toFixed(1)} degrees Fahrenheit`}
              onChange={(event) => setTemperature(Number(event.target.value))}
            />
            <div className="quick-values" aria-label="Quick temperature values">
              {[98.6, 100.4, 102].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={temperature === value ? "selected" : ""}
                  onClick={() => setTemperature(value)}
                >
                  {value}°
                </button>
              ))}
            </div>
          </div>
          <button
            className="response-button submit"
            type="button"
            onClick={onTemperature}
            disabled={busyAction !== null}
          >
            <Send size={18} />
            Record
          </button>
        </div>
      )}
    </section>
  );
}

function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <section className="timeline-wrap" aria-labelledby="timeline-heading">
      <div className="timeline-header">
        <h2 id="timeline-heading">Timeline</h2>
        <span>Chronological</span>
      </div>

      {events.length === 0 ? (
        <div className="empty-timeline">
          <Clock3 size={26} />
          <span>Waiting for the first instruction</span>
        </div>
      ) : (
        <ol className="timeline">
          {events.map((event) => (
            <li className={`event-row ${event.severity}`} key={event.id}>
              <time dateTime={event.created_at}>{formatTime(event.created_at)}</time>
              <article className="event-card">
                <div className="event-icon" aria-hidden="true">
                  {eventIcon(event)}
                </div>
                <div className="event-body">
                  <div className="event-meta">
                    <span>{actorLabel(event.actor)}</span>
                    {event.type === "alert_triggered" ? (
                      <strong>Alert</strong>
                    ) : null}
                  </div>
                  <h3>{event.title}</h3>
                  <p>{event.summary}</p>
                </div>
              </article>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
