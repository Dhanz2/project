# Campus Traffic Safety

A small Flask dashboard for reviewing campus traffic video. It uses YOLO vehicle tracking and OpenCV to flag possible movement against a configured gate direction, then lets a reviewer mark each event as verified, dismissed, or resolved.

## What it does

- Upload a short MP4, AVI, MOV, MKV, or WEBM clip.
- Track bicycles, cars, motorcycles, buses, and trucks across a virtual gate line.
- Save annotated video and snapshots when movement appears to oppose the selected direction.
- Review events and update their status in the incident dashboard.
- Store the incident database and media under `APP_DATA_DIR` so a mounted disk can preserve them between deployments.

The direction check is a simple demo heuristic based on a horizontal line through the frame. It is not a safety decision system, does not identify people, and can produce missed or incorrect alerts. Have an authorized person review every alert. Do not use this app for emergency response or upload footage without the required campus authorization and privacy controls.

## Run locally

Requires Python 3.11 or newer. Install dependencies and start the server:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The first video analysis may download the configured YOLO model. Set `YOLO_MODEL` to a local model path if desired. Set `APP_DATA_DIR` to choose where the SQLite database and generated media are stored.

## Deploy from GitHub with Render

1. Create a GitHub repository and push this project.
2. In Render, create a new Blueprint and select that repository. Render reads `render.yaml` and builds the Docker image.
3. Keep the persistent disk mounted at `/var/data`; the SQLite database, evidence snapshots, and annotated videos are written there.
4. In the Render service's environment settings, copy the generated `SAFETY_ADMIN_PASSWORD` secret for your authorized reviewers. The dashboard uses browser basic authentication with username `admin` and that password. Then open the service URL and upload a short authorized sample clip.

The included blueprint uses a persistent disk and one web worker because SQLite and locally stored media are intended for a single instance. For multiple app instances, replace SQLite and local media with managed database and object storage services. The hosted blueprint generates a shared password; local runs are open unless `SAFETY_ADMIN_PASSWORD` is set. Use your institution's approved access controls before handling real footage; this starter does not include individual user accounts or role-based permissions.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `PORT` | HTTP port | `5000` locally; set by host in deployment |
| `APP_DATA_DIR` | Database, temporary uploads, evidence, and processed video directory | `./instance` |
| `YOLO_MODEL` | YOLO weights name or path | `yolo26n.pt` |

Temporary uploaded source video is deleted after processing. Generated video and evidence are retained in the data directory. The app accepts files up to 100 MB.

## API

- `GET /api/health` — service health check
- `GET /api/stats` — dashboard totals
- `GET /api/incidents` — incident records
- `PATCH /api/incidents/<id>` — update review status
- `POST /api/analyze-video` — multipart video analysis (`video`, optional `location`, optional `expected_direction`)

## License and model

This repository's application code is provided under the MIT License. Ultralytics and its pretrained model have their own licensing terms; review those terms for your intended deployment before using pretrained weights commercially.

