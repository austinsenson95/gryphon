use std::{path::PathBuf, sync::Mutex, time::Duration};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 8000;
const HEALTH_ATTEMPTS: usize = 40;
const HEALTH_INTERVAL: Duration = Duration::from_millis(250);

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
#[allow(dead_code)]
pub enum RuntimePhase {
    #[default]
    Starting,
    Ready,
    Degraded,
    Disconnected,
    Restarting,
    Failed,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeSnapshot {
    state: RuntimePhase,
    detail: String,
    backend_url: String,
    pid: Option<u32>,
    owned: bool,
    restart_attempts: u8,
}

impl Default for RuntimeSnapshot {
    fn default() -> Self {
        Self {
            state: RuntimePhase::Starting,
            detail: "Checking Griffin Kernel".into(),
            backend_url: backend_url(),
            pid: None,
            owned: false,
            restart_attempts: 0,
        }
    }
}

struct RuntimeInner {
    snapshot: RuntimeSnapshot,
    child: Option<CommandChild>,
    generation: u64,
}

impl Default for RuntimeInner {
    fn default() -> Self {
        Self {
            snapshot: RuntimeSnapshot::default(),
            child: None,
            generation: 0,
        }
    }
}

#[derive(Default)]
pub struct RuntimeManager {
    inner: Mutex<RuntimeInner>,
}

fn backend_url() -> String {
    format!("http://{BACKEND_HOST}:{BACKEND_PORT}")
}

fn health_url() -> String {
    format!("{}/api/health", backend_url())
}

fn should_spawn(healthy: bool) -> bool {
    !healthy
}

impl RuntimeManager {
    pub fn snapshot(&self) -> RuntimeSnapshot {
        self.inner
            .lock()
            .expect("runtime mutex poisoned")
            .snapshot
            .clone()
    }

    fn publish(&self, app: &AppHandle, snapshot: RuntimeSnapshot) {
        self.inner.lock().expect("runtime mutex poisoned").snapshot = snapshot.clone();
        if let Err(error) = app.emit("griffin://runtime-state", &snapshot) {
            log::warn!("could not emit runtime state: {error}");
        }
    }

    async fn healthy(&self) -> bool {
        let response = reqwest::Client::new()
            .get(health_url())
            .timeout(Duration::from_millis(750))
            .send()
            .await;
        let Ok(response) = response else {
            return false;
        };
        if !response.status().is_success() {
            return false;
        }
        response
            .json::<serde_json::Value>()
            .await
            .map(|body| body["status"] == "ok" && body["service"] == "griffin")
            .unwrap_or(false)
    }

    async fn wait_until_ready(&self) -> bool {
        for _ in 0..HEALTH_ATTEMPTS {
            if self.healthy().await {
                return true;
            }
            tokio::time::sleep(HEALTH_INTERVAL).await;
        }
        false
    }

    fn development_python() -> Result<PathBuf, String> {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|path| path.parent())
            .ok_or_else(|| "could not resolve the Griffin repository root".to_string())?
            .to_path_buf();
        let venv_python = root.join(".venv/bin/python");
        if venv_python.is_file() {
            Ok(venv_python)
        } else {
            Err(format!(
                "development Python was not found at {}",
                venv_python.display()
            ))
        }
    }

    fn spawn_backend(
        &self,
        app: &AppHandle,
    ) -> Result<(tauri::async_runtime::Receiver<CommandEvent>, CommandChild), String> {
        let app_data = app
            .path()
            .app_data_dir()
            .map_err(|error| format!("could not resolve Griffin app data: {error}"))?;
        std::fs::create_dir_all(&app_data)
            .map_err(|error| format!("could not create Griffin app data: {error}"))?;
        let database_url = format!("sqlite:///{}", app_data.join("griffin.db").display());
        let args = ["--host", BACKEND_HOST, "--port", "8000"];
        let command = if cfg!(debug_assertions) {
            let python = Self::development_python()?;
            app.shell()
                .command(python)
                .args(["-m", "backend.desktop_entry"])
                .args(args)
                .current_dir(
                    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                        .parent()
                        .and_then(|path| path.parent())
                        .expect("repository root"),
                )
        } else {
            app.shell()
                .sidecar("griffin-kernel")
                .map_err(|error| format!("could not resolve packaged Griffin sidecar: {error}"))?
                .args(args)
        };
        command
            .env("GRIFFIN_RUNTIME_MODE", "desktop")
            .env("HOST", BACKEND_HOST)
            .env("PORT", BACKEND_PORT.to_string())
            .env("DATABASE_URL", database_url)
            .spawn()
            .map_err(|error| format!("could not spawn Griffin Kernel: {error}"))
    }

    pub async fn ensure_started(&self, app: &AppHandle) -> Result<(), String> {
        let initial = RuntimeSnapshot::default();
        self.publish(app, initial);

        if !should_spawn(self.healthy().await) {
            let snapshot = RuntimeSnapshot {
                state: RuntimePhase::Ready,
                detail: "Connected to an existing Griffin Kernel".into(),
                ..RuntimeSnapshot::default()
            };
            log::info!("backend already healthy; reusing existing instance");
            self.publish(app, snapshot);
            return Ok(());
        }

        let (mut events, child) = match self.spawn_backend(app) {
            Ok(process) => process,
            Err(error) => {
                self.publish(
                    app,
                    RuntimeSnapshot {
                        state: RuntimePhase::Failed,
                        detail: error.clone(),
                        ..RuntimeSnapshot::default()
                    },
                );
                return Err(error);
            }
        };
        let pid = child.pid();
        let generation = {
            let mut inner = self.inner.lock().expect("runtime mutex poisoned");
            inner.generation += 1;
            inner.child = Some(child);
            inner.generation
        };
        log::info!("spawned Griffin Kernel pid={pid}");
        self.publish(
            app,
            RuntimeSnapshot {
                state: RuntimePhase::Starting,
                detail: "Starting Griffin Kernel".into(),
                pid: Some(pid),
                owned: true,
                ..RuntimeSnapshot::default()
            },
        );

        let app_for_exit = app.clone();
        tauri::async_runtime::spawn(async move {
            while let Some(event) = events.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        log::debug!("kernel stdout: {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Stderr(line) => {
                        log::warn!("kernel stderr: {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Terminated(payload) => {
                        let manager = app_for_exit.state::<std::sync::Arc<RuntimeManager>>();
                        let mut inner = manager.inner.lock().expect("runtime mutex poisoned");
                        if inner.generation == generation && inner.snapshot.pid == Some(pid) {
                            inner.child = None;
                            inner.snapshot = RuntimeSnapshot {
                                state: RuntimePhase::Failed,
                                detail: format!(
                                    "Griffin Kernel exited{}",
                                    payload
                                        .code
                                        .map(|code| format!(" with code {code}"))
                                        .unwrap_or_default()
                                ),
                                pid: None,
                                owned: false,
                                restart_attempts: inner.snapshot.restart_attempts,
                                ..RuntimeSnapshot::default()
                            };
                            let snapshot = inner.snapshot.clone();
                            drop(inner);
                            log::error!("owned backend pid={pid} exited");
                            let _ = app_for_exit.emit("griffin://runtime-state", snapshot);
                        }
                        break;
                    }
                    _ => {}
                }
            }
        });

        if self.wait_until_ready().await {
            let snapshot = RuntimeSnapshot {
                state: RuntimePhase::Ready,
                detail: "Griffin Kernel is ready".into(),
                pid: Some(pid),
                owned: true,
                ..RuntimeSnapshot::default()
            };
            log::info!("backend ready pid={pid}");
            self.publish(app, snapshot);
            Ok(())
        } else {
            let detail = "Griffin Kernel did not become ready within 10 seconds".to_string();
            self.publish(
                app,
                RuntimeSnapshot {
                    state: RuntimePhase::Degraded,
                    detail: detail.clone(),
                    pid: Some(pid),
                    owned: true,
                    ..RuntimeSnapshot::default()
                },
            );
            Err(detail)
        }
    }

    pub async fn stop(&self) {
        let child = {
            let mut inner = self.inner.lock().expect("runtime mutex poisoned");
            inner.generation += 1;
            inner.child.take()
        };
        if let Some(child) = child {
            let pid = child.pid();
            match child.kill() {
                Ok(()) => log::info!("stopped owned Griffin Kernel pid={pid}"),
                Err(error) => log::warn!("could not stop owned Griffin Kernel pid={pid}: {error}"),
            }
        }
    }

    pub async fn restart(&self, app: &AppHandle) -> Result<RuntimeSnapshot, String> {
        let attempts = self.snapshot().restart_attempts.saturating_add(1);
        self.publish(
            app,
            RuntimeSnapshot {
                state: RuntimePhase::Restarting,
                detail: "Restarting Griffin Kernel".into(),
                restart_attempts: attempts,
                ..RuntimeSnapshot::default()
            },
        );
        self.stop().await;
        tokio::time::sleep(Duration::from_millis(300)).await;
        self.ensure_started(app).await?;
        let mut snapshot = self.snapshot();
        snapshot.restart_attempts = attempts;
        self.publish(app, snapshot.clone());
        Ok(snapshot)
    }
}

#[tauri::command]
pub fn runtime_status(runtime: State<'_, std::sync::Arc<RuntimeManager>>) -> RuntimeSnapshot {
    runtime.snapshot()
}

#[tauri::command]
pub async fn restart_backend(
    app: AppHandle,
    runtime: State<'_, std::sync::Arc<RuntimeManager>>,
) -> Result<RuntimeSnapshot, String> {
    runtime.restart(&app).await
}

#[cfg(test)]
mod tests {
    use super::{should_spawn, RuntimeManager, RuntimePhase};

    #[test]
    fn healthy_backend_is_reused() {
        assert!(!should_spawn(true));
        assert!(should_spawn(false));
    }

    #[test]
    fn runtime_starts_in_an_explicit_starting_state() {
        let snapshot = RuntimeManager::default().snapshot();
        assert_eq!(snapshot.state, RuntimePhase::Starting);
        assert!(!snapshot.owned);
        assert!(snapshot.pid.is_none());
    }
}
