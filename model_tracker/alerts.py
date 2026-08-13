import subprocess

_ANSI = True


def console_banner(title, lines):
    width = 90
    if _ANSI:
        print("\n" + "\033[1;33;41m" + " " * width + "\033[0m")
        print("\033[1;33;41m  NEW MODEL ALERT" + " " * (width - 16) + "\033[0m")
        for line in lines:
            text = f"  {line}"
            print("\033[1;33;41m" + text[:width].ljust(width) + "\033[0m")
        print("\033[1;33;41m" + " " * width + "\033[0m\n")
    else:
        print("\n" + "=" * width)
        print("NEW MODEL ALERT")
        for line in lines:
            print(f"  {line}")
        print("=" * width + "\n")


def desktop_toast(title, message):
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $tpl.GetElementsByTagName('text')
$nodes.Item(0).InnerText = '{title}'
$nodes.Item(1).InnerText = '{message}'
$toast = [Windows.UI.Notifications.ToastNotification]::new($tpl)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AI Model Tracker').Show($toast)
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            timeout=20, capture_output=True, check=False,
        )
    except Exception:
        pass
