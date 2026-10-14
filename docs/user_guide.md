# User guide

For operators and administrators of the installed Windows app. Developers: see the [README](../README.md).

## Install

1. Download the installer from the Releases page (`gpu` for NVIDIA computers, otherwise `cpu`) and verify it with `SHA256SUMS.txt`.
2. Run it. If Windows SmartScreen warns (the installer is not code-signed), choose **More info → Run anyway**.
3. The installer adds the Microsoft Visual C++ runtime and WebView2 if they are missing, and warns if no NVIDIA GPU is found.
4. Data lives in `C:\ProgramData\<ShortName>` (database, snapshots, backups, logs, `config`, `models`).

## Model files

Models are not part of the installer. See [models.md](models.md) for details.

1. General models (person detector and appearance model): open a terminal in the program folder and run `runtime\engine\python.exe -m engine.tools.download_models`. The files go to `<data folder>\models`.
2. PPE model: train your own and save it as `<data folder>\models\ppe.pt`. Nobody can supply it for you, because it depends on your cameras and equipment.

Without them the status bar shows the engine in **error** state and names the missing files. Once they are copied, restart the app.

## First run

Open the app from the desktop icon. The setup page asks for the site name, the default language and the administrator account. Afterwards the console opens. A tray icon keeps the app running; closing the window does not stop monitoring. Use the tray menu to open or quit.

## Screens

- **Overview**: the manager's summary. Pick **Today**, **7 days** or **30 days**. It shows the number of events (compared with the period before), critical and not-acknowledged events, violations still going on, a chart over time (per hour for today, per day otherwise), a breakdown by event type and by camera (click a row to see those events), and the open alarms that need attention. **Print report** opens the printable report for the same period.
- **Live**: one tile per camera with the engine's annotated picture. A tile turns red while an alarm is open. A **Recorded** badge marks cameras that play recorded footage instead of a real feed.
- **Events**: every violation as one row. Filter by date, camera, module, type, status or person; export CSV; open the print view for a PDF report.
- **Event detail**: snapshot, times, track IDs, number of occurrences, **Acknowledge**, and **Who is this?** to assign a person.
- **People** (administrators and operators): the list of employees you assign to events, and a profile page with 30-day statistics.
- **Settings** (administrators): users, cameras, modules, system check.

## Add cameras

**Settings → Cameras → Add.** Enter a name and a source: an RTSP/HTTP URL or a video file path. Choose the modules (empty means all enabled). The engine picks up changes within about 30 seconds; no restart is needed. Passwords inside RTSP URLs are hidden in the lists.

## Understand and handle events

An event is one violation over time. It starts when the violation has lasted long enough (`confirm_seconds`) and ends when it has been gone for `clear_seconds`. If the same person violates again within a few minutes the same event is reopened and **occurrences** goes up. Open alarms stay open until someone clicks **Acknowledge**; who and when is recorded.

## People

The engine never knows names. In **Event detail** use **Who is this?** to pick (or create) a person. Pages for that person then show their events. Deactivate a person instead of deleting them.

## Reports and backups

- **Export** (Events page) writes CSV with the current filters.
- **Print** opens a printable report; use the browser's *Save as PDF*.
- Events and snapshots older than the retention period (`retention_days`) are removed daily; the database is backed up daily into the `backups` folder (the newest 14 are kept).

## Update and uninstall

Run the newer installer over the old one; data is kept. To uninstall use **Apps → Installed apps**. The uninstaller asks whether to keep your data.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| Status bar: engine **offline** | The engine stopped or is starting. Wait a minute, then check `logs\engine.log` in the data folder. The launcher restarts it a few times, then gives up. |
| Engine **error**, missing models | Copy the model files (above) and restart. |
| No GPU / very slow | Install the NVIDIA driver, or accept CPU speed. Check **Settings → System check**. |
| Camera tile shows offline | Test the URL in a media player, check network and credentials, edit the camera. |
| "Port in use" | Another program uses the port. Close it, or restart the computer; the launcher picks a free port when it can. |
| App will not start twice | Only one copy runs; the second launch brings the first to the front. |
| Need to report a problem | Attach `engine.log`, `web.log` and `config\system_check.json` (they contain no passwords). |
