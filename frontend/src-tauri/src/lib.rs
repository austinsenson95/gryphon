mod native;
mod runtime;

use std::sync::{atomic::AtomicBool, Arc};

use runtime::RuntimeManager;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, RunEvent, WindowEvent,
};

struct AppControl {
    quitting: AtomicBool,
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Griffin", true, None::<&str>)?;
    let restart = MenuItem::with_id(
        app,
        "restart-kernel",
        "Restart Griffin Kernel",
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(app, "quit", "Quit Griffin", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &restart, &quit])?;

    TrayIconBuilder::with_id("griffin-tray")
        .tooltip("Griffin")
        .icon(
            app.default_window_icon()
                .cloned()
                .expect("Griffin app icon"),
        )
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "restart-kernel" => {
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    let manager = app.state::<Arc<RuntimeManager>>().inner().clone();
                    if let Err(error) = manager.restart(&app).await {
                        log::error!("backend restart failed: {error}");
                    }
                });
            }
            "quit" => {
                app.state::<AppControl>()
                    .quitting
                    .store(true, std::sync::atomic::Ordering::SeqCst);
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    app.state::<Arc<RuntimeManager>>().stop().await;
                    app.exit(0);
                });
            }
            _ => {}
        })
        .build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let runtime = Arc::new(RuntimeManager::default());
    let managed_runtime = runtime.clone();

    let app = tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .manage(runtime)
        .manage(AppControl {
            quitting: AtomicBool::new(false),
        })
        .invoke_handler(tauri::generate_handler![
            runtime::runtime_status,
            runtime::restart_backend,
            native::get_platform_info,
            native::show_notification,
            native::open_url,
        ])
        .setup(move |app| {
            build_tray(app)?;
            let handle = app.handle().clone();
            let manager = managed_runtime.clone();
            tauri::async_runtime::spawn(async move {
                if let Err(error) = manager.ensure_started(&handle).await {
                    log::error!("backend startup failed: {error}");
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                let quitting = window
                    .state::<AppControl>()
                    .quitting
                    .load(std::sync::atomic::Ordering::SeqCst);
                if !quitting {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Griffin");

    app.run(|handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            handle
                .state::<AppControl>()
                .quitting
                .store(true, std::sync::atomic::Ordering::SeqCst);
            let runtime = handle.state::<Arc<RuntimeManager>>().inner().clone();
            tauri::async_runtime::block_on(runtime.stop());
        }
    });
}
