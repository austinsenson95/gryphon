use serde::Serialize;
use tauri::AppHandle;
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_opener::OpenerExt;
use url::Url;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeResult {
    success: bool,
    message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PlatformInfo {
    os: &'static str,
    architecture: &'static str,
    family: &'static str,
}

fn validate_notification(title: &str, body: &str) -> Result<(), String> {
    let title_length = title.chars().count();
    let body_length = body.chars().count();
    if title.trim().is_empty() || title_length > 80 {
        return Err("title must contain between 1 and 80 characters".into());
    }
    if body_length > 500 {
        return Err("body must not exceed 500 characters".into());
    }
    Ok(())
}

fn validate_url(value: &str) -> Result<Url, String> {
    if value.len() > 2048 {
        return Err("URL must not exceed 2048 characters".into());
    }
    let url = Url::parse(value).map_err(|_| "URL is malformed".to_string())?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err("only HTTP and HTTPS URLs may be opened".into());
    }
    if url.host_str().is_none() {
        return Err("URL must include a host".into());
    }
    Ok(url)
}

#[tauri::command]
pub fn get_platform_info() -> PlatformInfo {
    PlatformInfo {
        os: std::env::consts::OS,
        architecture: std::env::consts::ARCH,
        family: std::env::consts::FAMILY,
    }
}

#[tauri::command]
pub fn show_notification(
    app: AppHandle,
    title: String,
    body: String,
) -> Result<NativeResult, String> {
    validate_notification(&title, &body)?;
    app.notification()
        .builder()
        .title(title)
        .body(body)
        .show()
        .map_err(|error| {
            log::error!("native notification failed: {error}");
            "macOS could not show the notification".to_string()
        })?;
    Ok(NativeResult {
        success: true,
        message: "notification shown".into(),
    })
}

#[tauri::command]
pub fn open_url(app: AppHandle, url: String) -> Result<NativeResult, String> {
    let validated = validate_url(&url)?;
    app.opener()
        .open_url(validated.as_str(), None::<&str>)
        .map_err(|error| {
            log::error!("native URL open failed: {error}");
            "macOS could not open the URL".to_string()
        })?;
    Ok(NativeResult {
        success: true,
        message: "URL opened".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::{validate_notification, validate_url};

    #[test]
    fn notification_arguments_are_bounded() {
        assert!(validate_notification("Griffin", "Ready").is_ok());
        assert!(validate_notification("", "Ready").is_err());
        assert!(validate_notification(&"x".repeat(81), "Ready").is_err());
        assert!(validate_notification("Griffin", &"x".repeat(501)).is_err());
    }

    #[test]
    fn url_command_rejects_shell_and_file_inputs() {
        assert!(validate_url("https://griffin.example/status").is_ok());
        assert!(validate_url("file:///etc/passwd").is_err());
        assert!(validate_url("sh -c 'rm -rf /'").is_err());
        assert!(validate_url("javascript:alert(1)").is_err());
    }
}
