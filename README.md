# insurance-claim-backend

## Import Job Workflow

The client vehicle, vehicle owner, and engineer detail imports now run asynchronously. Each upload returns a job handle that the frontend can poll until processing finishes.

### Start An Import

`POST /client-vehicles/import-client-vehicle/`  
`POST /vehicle-owners/import-vehicle-owner/`  
`POST /engineer-details/import-engineer-detail/`

| Field | Type | Notes |
| --- | --- | --- |
| `claim_id` | query | Required claim identifier |
| `files` | multipart (list) | One or more PDF/image files |

Response `202 Accepted`

```json
{
  "job_id": "0b8dbe50-9b5e-4c3c-9a23-7de8c7a7287e",
  "status": "pending"
}
```

### Poll Job Status

`GET /import-jobs/{job_id}/status`

#### Sample Response

```json
{
  "job_id": "0b8dbe50-9b5e-4c3c-9a23-7de8c7a7287e",
  "job_type": "client_vehicle_import",
  "status": "processing",
  "created_at": "2025-11-11T12:00:00.000000+00:00",
  "updated_at": "2025-11-11T12:00:05.000000+00:00",
  "error": null
}
```

When `status` becomes `completed`, fetch the cached output. If `status` is `failed`, the `error` field contains the message.

### Retrieve Import Result

`GET /import-jobs/{job_id}/result`

- `200 OK` when processing is complete.
- `202 Accepted` while the job is still running.
- `500 Internal Server Error` for failed jobs (payload includes the `job_id` and `error` message).

#### Successful Responses

Client vehicle import:

```json
{
  "job_id": "…",
  "status": "completed",
  "result": {
    "client_vehicle_detail": { "...": "…" },
    "uploaded_files": [
      {
        "file_name": "V5C.pdf",
        "file_path": "/history/123/20250101120000/V5C.pdf"
      }
    ]
  }
}
```

Vehicle owner import:

```json
{
  "job_id": "…",
  "status": "completed",
  "result": {
    "vehicle_owner_detail": [
      { "first_name": "Jane", "surname": "Doe", "...": "…" }
    ],
    "uploaded_files": [ { "file_name": "owner.pdf", "file_path": "/…" } ]
  }
}
```

Engineer detail import:

```json
{
  "job_id": "…",
  "status": "completed",
  "result": {
    "engineer_detail": [
      { "company_name": "ABC Engineering", "...": "…" }
    ],
    "uploaded_files": [ { "file_name": "instruction.pdf", "file_path": "/…" } ]
  }
}
```

## Roboflow Inference (Vehicle Damage Detection)

Damage detection runs through the Roboflow workflow **"Detect, Count, and Visualize 3"**
(`detect-count-and-visualize-3`) via `RoboflowService` (`src/appflow/services/roboflow_service.py`),
which uses the official `inference-sdk` `InferenceHTTPClient`.

Configuration is environment-driven (`.env`):

| Variable | Default | Notes |
| --- | --- | --- |
| `ROBOFLOW_API_KEY` | — | From app.roboflow.com/settings/api. **Never commit.** |
| `ROBOFLOW_API_URL` | `https://serverless.roboflow.com` | Point at a self-hosted `inference` server (e.g. `http://localhost:9001`) to avoid serverless usage limits. |
| `ROBOFLOW_WORKSPACE` | `marwas-workspace-sogsw` | Workspace slug. |
| `ROBOFLOW_WORKFLOW_ID` | `detect-count-and-visualize-3` | Workflow slug. |

The workflow takes a single `image` input. Image-shaped outputs (annotated frames) are
returned as base64 and written to disk — they are never logged or held in memory.

> **Usage limits:** Roboflow serverless inference is metered **per account/API key**, not per
> workflow. Making a model "public" lets others run it, but calls made with your own key still
> consume your quota. To truly remove the limit, run inference on a self-hosted `inference`
> server and set `ROBOFLOW_API_URL` to it.

### Run inference locally (removes the serverless limit)

Serverless metering is per account, so switching workflows alone won't lift the limit. Run the
Roboflow `inference` server yourself — inference then executes locally and is **not** metered.

1. Start the inference server (CPU image; use `-gpu` if you have CUDA):

   ```bash
   docker run -d --name inference -p 9001:9001 roboflow/roboflow-inference-server-cpu:latest
   # or, without Docker:  pip install inference-cli && inference server start
   ```

   It listens on `http://localhost:9001`. `ROBOFLOW_API_KEY` is still needed the first time so the
   server can pull the (public) model weights; after that, inference runs locally.

2. Point the backend at it in `.env` and restart:

   ```env
   ROBOFLOW_API_URL=http://localhost:9001
   # if the backend itself runs in Docker, use http://host.docker.internal:9001
   ```

3. Verify connectivity:

   ```
   GET /car-damage-detection/health
   → { "reachable": true, "self_hosted": true, "api_url": "http://localhost:9001", ... }
   ```

No application code changes are needed — only `ROBOFLOW_API_URL`.
