fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "runtime_status",
            "restart_backend",
            "get_platform_info",
            "show_notification",
            "open_url",
        ]),
    ))
    .expect("failed to build Griffin's Tauri permissions")
}
