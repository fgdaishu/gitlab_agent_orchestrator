# Troubleshooting

## Label Does Not Trigger

- Confirm the GitLab webhook points to `http://<orchestrator-host-ip>:8080/gitlab/webhook`.
- Confirm the webhook secret matches `GITLAB_WEBHOOK_SECRET`.
- Confirm issue events are enabled in GitLab.
- Remove and re-add one of: `agent:opencode`, `agent:codex`, `agent:gemini`.
- Check API health with `scripts/status.ps1`.

## Job Fails Before Agent Starts

- Check `GET /jobs/<job_id>` and `GET /jobs/<job_id>/log`.
- Check `.env` has `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_WEBHOOK_SECRET`, and `AGENT_EXECUTION_BACKEND=docker_project`.
- Check the Docker image exists: `docker images --format "{{.Repository}}:{{.Tag}}"`.

## Agent Auth

- OpenCode smoke tests should use `SANDBOX_OPENCODE_MODEL=opencode/big-pickle`.
- Codex login command:

```powershell
docker exec -it gitlab-agent-project-<project_id> codex login --device-auth
```

- Gemini login command:

```powershell
docker exec -it gitlab-agent-project-<project_id> gemini
```

## Docker Sandbox

- Project container name: `gitlab-agent-project-<project_id>`.
- Project volume name: `gitlab-agent-project-<project_id>-workspace`.
- Repo inside container: `/workspace/repo`.
- Rebuild a sandbox only when the user accepts losing that project container/volume state:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/projects/<project_id>/sandbox/rebuild
```

## GitLab Comment Write Failures

The GitLab REST client disables urllib environment proxies. If comments still do not appear, check GitLab availability and token permissions before changing webhook handling.
