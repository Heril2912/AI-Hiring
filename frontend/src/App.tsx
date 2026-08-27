import { useEffect, useState } from "react";
import { ResumeUpload } from "./components/ResumeUpload";

type HealthResponse = {
  status: string;
  service: string;
  database: string;
};

type ConnectionState = "checking" | "connected" | "unavailable";

export function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        const response = await fetch("/api/v1/health", {
          signal: controller.signal,
        });

        if (!response.ok) {
          setConnectionState("unavailable");
          return;
        }

        const data: HealthResponse = await response.json();

        if (data.status === "healthy" && data.database === "connected") {
          setConnectionState("connected");
        } else {
          setConnectionState("unavailable");
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setConnectionState("unavailable");
        }
      }
    }

    checkHealth();

    return () => {
      controller.abort();
    };
  }, []);

  return (
    <div className="container">
      <header className="app-header">
        <h1>AI-Driven Smart Hiring Platform</h1>
        <p className="description">Evidence-based resume parsing and candidate profiling</p>
      </header>

      <div className="status-card">
        <p className="status-label">System foundation</p>
        <div className="status-indicator-wrapper">
          <span className={`status-dot ${connectionState}`} />
          <span className="status-text">
            {connectionState === "checking" && "Checking services..."}
            {connectionState === "connected" && "Backend and database connected"}
            {connectionState === "unavailable" && "Backend or database unavailable"}
          </span>
        </div>
      </div>

      <main className="app-main">
        <ResumeUpload />
      </main>
    </div>
  );
}

export default App;
